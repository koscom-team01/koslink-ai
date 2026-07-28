"""kosLINK AI - 뉴스 분석 오케스트레이션 서비스.

흐름 (docs/rag_architecture.md 7장 "API 처리 흐름" 참고):
    [0] 미응답 뉴스 선점        news_repository.claim_pending - status='PENDING'인
                              뉴스를 'ANALYZING'으로 선점해 배치로 가져옴. 여기까지만
                              analyze_pending이 응답 전에 동기로 처리하고, [1]~[7]은
                              전부 BackgroundTasks로 미뤄 응답 이후에 실행한다 -
                              백엔드가 호출할 때마다 LLM/RAG 파이프라인이 끝날 때까지
                              기다리지 않게 하기 위함(analyze_pending/_analyze_and_save
                              참고). 응답의 status="accepted"는 선점됐다는 뜻이지
                              완료를 뜻하지 않으며, 실제 완료/실패는 news.status와
                              ai_responses로 별도 확인해야 한다.
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
from app.config import get_settings
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
        """claim_pending(선점)까지만 응답 전에 동기로 처리하고, LLM/RAG 분석·저장·
        사후 임베딩은 전부 BackgroundTasks로 미뤄서 응답 이후에 실행한다. 백엔드가
        호출할 때마다 파이프라인이 끝날 때까지 기다릴 필요가 없게 하기 위함 -
        claim_pending은 단일 UPDATE...RETURNING이라 빨라서 동기로 둬도 응답
        지연에 영향이 거의 없고, 오히려 이번 호출이 어떤 뉴스를 선점했는지
        응답으로 바로 알려줄 수 있어 남겨둔다.

        BackgroundTasks 안에서 또 background_tasks.add_task를 호출해도 안전하다 -
        Starlette BackgroundTasks.__call__이 `for task in self.tasks`로 단순
        리스트 순회라서, 실행 중 append된 항목(_trigger_post_response_embedding)도
        같은 루프가 이어서 처리하고, 요청 스코프 DB 세션도 그동안 안 닫힌다.

        응답의 status="accepted"는 처리 완료를 뜻하지 않는다 - 실제 완료/실패
        여부는 news.status와 ai_responses를 통해 확인해야 한다(docs/rag_architecture.md
        7장 계약 - AI 서버가 DB에 쓰고 백엔드/FE는 DB를 읽는 구조)."""
        pending = await self._news_repo.claim_pending(limit)
        logger.info("[0/7] 미응답 뉴스 선점 완료 - %d건 (news_ids=%s)", len(pending), [n.news_id for n in pending])

        for news in pending:
            background_tasks.add_task(self._analyze_and_save, news, background_tasks)

        return [PendingAnalysisResult(news_id=news.news_id, status="accepted") for news in pending]

    async def _analyze_and_save(self, news: NewsRecord, background_tasks: BackgroundTasks) -> None:
        logger.info("[news_id=%s] 분석 파이프라인 시작", news.news_id)
        try:
            analyzed = await self._analyze(news)
            if analyzed is not None:
                response, evidence_debug = analyzed
                await self._response_repo.save(news.news_id, response, evidence_debug)
                logger.info("[news_id=%s] [6/7] ai_responses 저장 완료", news.news_id)
            else:
                logger.info("[news_id=%s] [6/7] 저장 스킵 - 유니버스 밖 뉴스(관련 응답 없음)", news.news_id)
            await self._news_repo.mark_done(news.news_id)
            logger.info("[news_id=%s] news.status=DONE 처리 완료", news.news_id)
            if get_settings().POST_RESPONSE_EMBEDDING_ENABLED:
                background_tasks.add_task(self._trigger_post_response_embedding, news)
                logger.info("[news_id=%s] [7/7] 사후 임베딩 백그라운드 예약", news.news_id)
        except Exception as e:
            logger.exception("[news_id=%s] 분석 실패", news.news_id)
            await self._response_repo.save_failure(news.news_id, str(e))
            await self._news_repo.mark_failed(news.news_id)
            logger.info("[news_id=%s] news.status=FAILED 처리", news.news_id)

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
        logger.info(
            "[news_id=%s] [1/7] LLM 추출 완료 - origin_stocks=%s",
            news.news_id, [s.ticker for s in extraction.origin_stocks],
        )

        if not extraction.origin_stocks:
            logger.info("[news_id=%s] [1/7] origin_stocks 없음 - 유니버스 밖 뉴스, 이후 단계 스킵", news.news_id)
            return None

        derived_candidates, origin_id, graph_nodes, graph_edges = await self._explore_ontology(
            extraction.origin_stocks
        )
        logger.info(
            "[news_id=%s] [2/7] 온톨로지 조회 완료 - candidates=%d, nodes=%d, edges=%d",
            news.news_id, len(derived_candidates), len(graph_nodes), len(graph_edges),
        )
        news_summary_text = " ".join(extraction.news_summary)
        vector_context = await self._collect_evidence(derived_candidates, extraction.origin_stocks, news_summary_text)
        logger.info("[news_id=%s] [3/7] RAG 근거 수집 완료 - evidence=%d건", news.news_id, len(vector_context))
        synthesis = await synthesize_related_stocks(
            news, extraction.origin_stocks, derived_candidates, vector_context
        )
        logger.info(
            "[news_id=%s] [4/7] LLM 종합 완료 - related_stocks=%d",
            news.news_id, len(synthesis.related_stocks),
        )

        candidates_by_ticker = {c.ticker: c for c in derived_candidates}
        evidence_by_ticker = group_evidence_by_ticker(vector_context)

        # 프롬프트로 "후보 목록에 없는 기업을 새로 만들어내지 마세요"라고 지시해도
        # LLM이 origin_stocks 자신 등 후보 밖 기업을 끼워 넣는 경우가 실제로
        # 있어서, 온톨로지 후보에 없는 항목은 걸러낸다 (하드 팩트가 없는
        # related_stocks는 relation_label/relation_path를 채울 수 없어 신뢰 불가).
        # name이 아니라 ticker로만 매칭한다 - 후보 목록엔 "이름(티커)"로 노출되는데
        # 티커는 자연어 변형 여지가 없어 LLM이 그대로 echo하지만, 이름은 띄어쓰기·
        # "㈜" 유무 등으로 미세하게 달라질 수 있어 (ticker, name) 조합으로 매칭하면
        # 실제로는 유효한 응답을 이름 표기 차이만으로 조용히 떨어뜨리는 문제가 있었다.
        # 매칭된 뒤엔 name도 candidate(온톨로지 원본) 쪽을 써서 표기를 통일한다.
        related_stocks: list[RelatedStock] = []
        evidence_debug: list[EvidenceDebugEntry] = []
        for r in synthesis.related_stocks:
            candidate = candidates_by_ticker.get(r.ticker)
            if candidate is None:
                logger.warning(
                    "synthesize_related_stocks가 후보 목록에 없는 ticker를 반환 - "
                    "news_id=%s ticker=%s name=%s",
                    news.news_id, r.ticker, r.name,
                )
                continue
            related_stocks.append(
                RelatedStock(
                    ticker=candidate.ticker,
                    name=candidate.name,
                    status=r.status,
                    relation_label=candidate.relation_label,
                    relation_path=candidate.relation_path,
                    propagation=r.propagation,
                )
            )
            evidence_debug.append(
                EvidenceDebugEntry(
                    ticker=candidate.ticker,
                    name=candidate.name,
                    evidence_source=r.evidence_source,
                    retrieved_evidence=[
                        EvidenceSnippet(
                            source_type=e["source_type"],
                            title=e["title"],
                            published_date=e["published_date"],
                            excerpt=e["text"][:200],
                        )
                        for e in evidence_by_ticker.get(candidate.ticker, [])
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
        logger.info("[news_id=%s] [5/7] 응답 조립 완료 - related_stocks=%d", news.news_id, len(related_stocks))

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
        asyncio.gather로 동시에 실행한다.

        검색 쿼리는 뉴스 요약만이 아니라 candidate.relation_path(온톨로지가 찾은
        공급망 관계 - 예: "SK하이닉스향 실리콘 부품 공급")를 같이 붙여서 임베딩한다.
        뉴스 요약만으로 검색하면 "반도체 주가 하락류"의 일반적인 유사 청크만 걸려서
        해당 후보-관계에 특화된 근거를 못 찾는 경우가 많았다 - 관계 문구를 쿼리에
        포함하면 그 관계를 실제로 뒷받침하는 청크를 찾을 확률이 올라간다. 후보마다
        쿼리가 달라지므로 임베딩도 후보별로 계산한다(이전엔 루프 밖에서 한 번만
        계산했으나 관계 특화 검색을 위해 포기)."""
        if not derived_candidates:
            return []

        async def _collect_for_candidate(candidate: DerivedCompanyCandidate) -> list[dict]:
            query_text = f"{news_summary_text} {candidate.relation_path}"
            embedding = await get_embedding_provider().aembed_query(query_text)
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
        logger.info("[news_id=%s] [7/7] 사후 임베딩 시작", news.news_id)
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
            logger.info("[news_id=%s] [7/7] 사후 임베딩 완료 - rag_embedded_at 갱신", news.news_id)
        except Exception:
            logger.exception("[news_id=%s] [7/7] 사후 임베딩 실패", news.news_id)
