"""kosLINK AI - 뉴스 분석 오케스트레이션 서비스.

흐름 (docs/rag_architecture.md 7장 "API 처리 흐름" 참고):
    [0] 미응답 뉴스 선점        news_repository.claim_pending - status='PENDING'인
                              뉴스를 'ANALYZING'으로 선점해 배치로 가져옴
    [1] LLM 추출              qa_chain.extract_key_companies -> news_summary, origin_stocks
                              (companies 유니버스 전체를 프롬프트에 같이 넣어 그
                              밖의 기업을 지어내지 못하게 제한, origin_stocks는
                              최대 1개. 비어 있으면 - 즉 유니버스 밖 뉴스면 -
                              _analyze가 여기서 바로 None을 반환하고 [2]~[5]를
                              전부 건너뜀)
    [2] 온톨로지 조회          _explore_ontology - origin_stock 티커마다
                              ontology_client.find_related_companies(ticker)를 호출해
                              related_stocks 후보와 graph(2-hop 노드/엣지)를 함께 받고,
                              origin_stocks가 여럿이면 결과를 합침
    [3] RAG 근거 검색          _collect_evidence - find_mentions(키워드 직접 근거) +
                              similarity_search(뉴스 요약 기반 의미 유사도 근거)
    [4] LLM 종합              qa_chain.synthesize_related_stocks -> related_stocks, final_summary
                              (연관기업 후보가 없어도 final_summary는 항상 필요해서
                              스킵하지 않고 매번 호출)
    [5] 응답 조립              related_stocks의 ticker/name/relation_label/relation_path는
                              derived_candidates(온톨로지 하드 팩트)에서 그대로 가져오고,
                              status/propagation만 [4] 결과로 채움. graph는 [2]에서 받은
                              노드/엣지를 그대로 패싱하고 newsId만 RAG가 채움. 동시에
                              evidence_debug(related_stock별 evidence_source +
                              실제 검색된 근거 청크)를 응답과 별도로 조립 - RAG
                              적중률 분석용, FE 응답 계약엔 없음
    [6] 응답 저장              _analyze가 None이 아닐 때만 response_repository.save
                              (response + evidence_debug), news_repository.mark_done은
                              항상 호출(관련 기업이 없는 것도 정상 처리 완료로 취급)
    [7] 사후 임베딩 트리거      _trigger_post_response_embedding - 실패해도 응답에
                              영향 없는 best-effort라 BackgroundTasks로 응답 반환 후
                              실행되게 미뤄서, OpenAI 임베딩 API 지연이 HTTP 응답
                              시간(및 게이트웨이 타임아웃)에 영향을 못 미치게 한다

배치 안에서 뉴스 1건이 실패해도(LLM 오류 등) 나머지 뉴스 처리는 계속 진행한다 -
news_repository.mark_failed + response_repository.save_failure로 실패를 기록하고
다음 뉴스로 넘어간다 (analyze_pending 참고).
"""

import asyncio
import logging

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chains.qa_chain import (
    DerivedCompanyCandidate,
    extract_key_companies,
    group_evidence_by_ticker,
    synthesize_related_stocks,
)
from app.core.embeddings.factory import get_embedding_provider
from app.repositories.company_repository import CompanyRepository
from app.repositories.news_repository import NewsRecord, NewsRepository
from app.repositories.ontology_client import find_related_companies
from app.repositories.response_repository import ResponseRepository
from app.repositories.vector_repository import VectorRepository
from app.schemas.news_analysis import (
    EvidenceDebugEntry,
    EvidenceSnippet,
    Graph,
    GraphEdge,
    GraphNode,
    NewsAnalysisResponse,
    OriginStock,
    PendingAnalysisResult,
    RelatedStock,
    Source,
)
from app.services.ingestion_service import achunk_and_store, build_async_vector_store
from app.utils.text_splitter import build_prefix

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, session: AsyncSession):
        self._news_repo = NewsRepository(session)
        self._company_repo = CompanyRepository(session)
        self._vector_repo = VectorRepository(session)
        self._response_repo = ResponseRepository(session)

    async def analyze_pending(
        self, limit: int, background_tasks: BackgroundTasks
    ) -> list[PendingAnalysisResult]:
        pending = await self._news_repo.claim_pending(limit)

        results = []
        for news in pending:
            try:
                analyzed = await self._analyze(news)
                if analyzed is not None:
                    response, evidence_debug = analyzed
                    await self._response_repo.save(news.news_id, response, evidence_debug)
                await self._news_repo.mark_done(news.news_id)
                background_tasks.add_task(self._trigger_post_response_embedding, news)
                results.append(PendingAnalysisResult(news_id=news.news_id, status="done"))
            except Exception as e:
                logger.exception("뉴스 분석 실패 - news_id=%s", news.news_id)
                await self._response_repo.save_failure(news.news_id, str(e))
                await self._news_repo.mark_failed(news.news_id)
                results.append(PendingAnalysisResult(news_id=news.news_id, status="failed", error=str(e)))
        return results

    async def _analyze(
        self, news: NewsRecord
    ) -> tuple[NewsAnalysisResponse, list[EvidenceDebugEntry]] | None:
        """뉴스 1건을 분석한다. origin_stocks가 비면(51개 유니버스와 무관한 뉴스)
        None을 반환해 이후 온톨로지/RAG/종합 단계를 전부 건너뛴다 - analyze_pending은
        이 경우 ai_responses 행을 만들지 않고 news.status만 DONE으로 남긴다(실패가
        아니라 "분석할 대상이 없음"이라 news 재처리 대상에서는 정상적으로 빠짐).

        evidence_debug는 응답(NewsAnalysisResponse)과 별도로 반환한다 - FE 응답
        계약에는 없고 ai_responses.evidence_debug 컬럼에만 저장되는, RAG 적중률
        분석용 내부 데이터라서 섞지 않는다 (schemas/news_analysis.py의
        EvidenceDebugEntry 참고).
        """
        companies = await self._company_repo.list_all()
        extraction = await extract_key_companies(news, companies)

        if not extraction.origin_stocks:
            return None

        derived_candidates, origin_id, graph_nodes, graph_edges = await self._explore_ontology(
            extraction.origin_stocks
        )
        news_summary_text = " ".join(extraction.news_summary)
        vector_context = await self._collect_evidence(derived_candidates, extraction.origin_stocks, news_summary_text)
        synthesis = await synthesize_related_stocks(
            news, extraction.origin_stocks, derived_candidates, vector_context
        )

        candidates_by_key = {(c.ticker, c.name): c for c in derived_candidates}
        evidence_by_ticker = group_evidence_by_ticker(vector_context)

        # 프롬프트로 "후보 목록에 없는 기업을 새로 만들어내지 마세요"라고 지시해도
        # LLM이 origin_stocks 자신 등 후보 밖 기업을 끼워 넣는 경우가 실제로
        # 있어서, 온톨로지 후보에 없는 항목은 조용히 걸러낸다 (하드 팩트가 없는
        # related_stocks는 relation_label/relation_path를 채울 수 없어 신뢰 불가).
        related_stocks: list[RelatedStock] = []
        evidence_debug: list[EvidenceDebugEntry] = []
        for r in synthesis.related_stocks:
            candidate = candidates_by_key.get((r.ticker, r.name))
            if candidate is None:
                continue
            related_stocks.append(
                RelatedStock(
                    ticker=r.ticker,
                    name=r.name,
                    status=r.status,
                    relation_label=candidate.relation_label,
                    relation_path=candidate.relation_path,
                    propagation=r.propagation,
                )
            )
            evidence_debug.append(
                EvidenceDebugEntry(
                    ticker=r.ticker,
                    name=r.name,
                    evidence_source=r.evidence_source,
                    retrieved_evidence=[
                        EvidenceSnippet(
                            source_type=e["source_type"],
                            title=e["title"],
                            published_date=e["published_date"],
                            excerpt=e["text"][:200],
                        )
                        for e in evidence_by_ticker.get(r.ticker, [])
                    ],
                )
            )

        response = NewsAnalysisResponse(
            news_summary=extraction.news_summary,
            source=Source(
                press=news.press,
                published_at=str(news.published_at) if news.published_at else None,
                url=news.url,
            ),
            origin_stocks=extraction.origin_stocks,
            related_stocks=related_stocks,
            final_summary=synthesis.final_summary,
            graph=Graph(newsId=str(news.news_id), originId=origin_id, nodes=graph_nodes, edges=graph_edges),
        )

        return response, evidence_debug

    async def _explore_ontology(
        self, origin_stocks: list[OriginStock]
    ) -> tuple[list[DerivedCompanyCandidate], str, list[GraphNode], list[GraphEdge]]:
        """origin_stock 티커마다 온톨로지(2-hop) 탐색 결과를 합친다.

        ontology_client.find_related_companies(ticker)가 related_stocks(연관기업
        후보)와 graph(노드/엣지)를 한 번에 반환하므로 같이 처리한다. origin_stocks가
        여럿이면 각 결과를 (ticker, name)/node id 기준으로 중복 제거하며 합치고,
        originId는 가장 먼저 나온 결과를 쓴다.
        """
        candidates: dict[tuple[str, str], DerivedCompanyCandidate] = {}
        nodes: dict[str, GraphNode] = {}
        edges: dict[str, GraphEdge] = {}
        origin_id = ""

        for origin_stock in origin_stocks:
            if not origin_stock.ticker:
                continue
            result = await find_related_companies(origin_stock.ticker)
            for fact in result.related_stocks:
                dedup_key = (fact.ticker, fact.name)
                candidates.setdefault(
                    dedup_key,
                    DerivedCompanyCandidate(
                        ticker=fact.ticker,
                        name=fact.name,
                        relation_label=fact.relation_label,
                        relation_path=fact.relation_path,
                    ),
                )
            origin_id = origin_id or result.graph.originId
            for node in result.graph.nodes:
                nodes.setdefault(node.id, GraphNode(**node.model_dump()))
            for edge in result.graph.edges:
                edges.setdefault(edge.id, GraphEdge(**edge.model_dump()))

        return list(candidates.values()), origin_id, list(nodes.values()), list(edges.values())

    async def _collect_evidence(
        self,
        derived_candidates: list[DerivedCompanyCandidate],
        origin_stocks: list[OriginStock],
        news_summary_text: str,
    ) -> list[dict]:
        """후보 기업마다 순차로 DB조회+임베딩 API를 호출하면 후보 수만큼 네트워크
        왕복이 그대로 쌓여 지연 시간이 늘어난다 - 후보별 근거 수집은 서로 독립적이라
        asyncio.gather로 동시에 실행하고, 뉴스 요약 임베딩도 후보마다 재계산하지 않게
        루프 밖에서 한 번만 구한다."""
        if not derived_candidates:
            return []

        embedding = await get_embedding_provider().aembed_query(news_summary_text)

        async def _collect_for_candidate(candidate: DerivedCompanyCandidate) -> list[dict]:
            mention_results = await asyncio.gather(
                *[
                    self._vector_repo.find_mentions(candidate.ticker, origin_stock.name)
                    for origin_stock in origin_stocks
                ]
            )
            similarity_result = await self._vector_repo.similarity_search_by_vector(candidate.ticker, embedding)
            return [item for mentions in mention_results for item in mentions] + similarity_result

        results = await asyncio.gather(*[_collect_for_candidate(c) for c in derived_candidates])
        return [item for candidate_evidence in results for item in candidate_evidence]

    async def _trigger_post_response_embedding(self, news: NewsRecord) -> None:
        """분석 응답 저장 후 같은 뉴스를 pgvector에 사후 임베딩 (rag_architecture.md 0장/8장).

        실패해도 분석 응답 자체엔 영향 없어야 하므로 예외를 삼키고 로그만 남긴다 -
        다음 폴링에서 재시도되는 게 아니라 이 뉴스는 영구히 근거 코퍼스에서 빠지게
        되지만(rag_embedded_at이 NULL로 남음), 최소한 사용자에게 보여줄 분석 응답은
        지켜야 한다는 우선순위다.
        """
        try:
            prefix = build_prefix(news.title)
            metadata = {
                "ticker": None,
                "source_type": "news",
                "source_doc_id": str(news.news_id),
                "title": news.title,
                "url": news.url,
                "published_date": str(news.published_at) if news.published_at else None,
            }
            await achunk_and_store([(prefix, news.body, metadata)], build_async_vector_store())
            await self._news_repo.mark_embedded(news.news_id)
        except Exception:
            logger.exception("사후 임베딩 실패 - news_id=%s", news.news_id)
