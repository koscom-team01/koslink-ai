"""kosLINK AI - 뉴스 분석 오케스트레이션 서비스.

흐름 (docs/rag_architecture.md 7장 "API 처리 흐름" 참고):
    [1] 뉴스 조회             news_repository.get_by_id
    [2] LLM 추출              qa_chain.extract_key_companies -> news_summary, key_companies
    [3] 온톨로지 조회          _find_derived_candidates - 자리표시자, 항상 [] (온톨로지 파트 작업 전)
    [4] RAG 근거 검색          _collect_evidence - vector_repository.find_mentions만 사용
                              (similarity_search는 core/embeddings/* 없어서 아직 못 씀)
    [5] LLM 종합              qa_chain.synthesize_derived_companies -> derived_companies
    [6] 응답 조립              _to_evidence_sources로 vector_context를 매칭해 붙임
    [7] 응답 저장              response_repository.save
    [8] 사후 임베딩 트리거      _trigger_post_response_embedding - 자리표시자, no-op

[3]이 항상 빈 리스트라 [4][5]도 지금은 실질적으로 항상 빈 결과가 된다 - 온톨로지/
임베딩 파트 작업이 끝나면 [3]만 실제 구현으로 교체하면 나머지는 그대로 동작한다.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chains.qa_chain import (
    DerivedCompanyCandidate,
    extract_key_companies,
    synthesize_derived_companies,
)
from app.repositories.news_repository import NewsRecord, NewsRepository
from app.repositories.response_repository import ResponseRepository
from app.repositories.vector_repository import VectorRepository
from app.schemas.news_analysis import DerivedCompany, EvidenceSource, KeyCompany, NewsAnalysisResponse

logger = logging.getLogger(__name__)


class NewsNotFoundError(Exception):
    def __init__(self, news_id: int):
        self.news_id = news_id
        super().__init__(f"news_id={news_id}를 찾을 수 없습니다")


class RetrievalService:
    def __init__(self, session: AsyncSession):
        self._news_repo = NewsRepository(session)
        self._vector_repo = VectorRepository(session)
        self._response_repo = ResponseRepository(session)

    async def analyze(self, news_id: int) -> NewsAnalysisResponse:
        news = await self._news_repo.get_by_id(news_id)
        if news is None:
            raise NewsNotFoundError(news_id)

        extraction = await extract_key_companies(news)
        derived_candidates = await self._find_derived_candidates(extraction.key_companies)
        vector_context = await self._collect_evidence(derived_candidates, extraction.key_companies)
        llm_derived = await synthesize_derived_companies(
            news, extraction.key_companies, derived_candidates, vector_context
        )

        response = NewsAnalysisResponse(
            news_summary=extraction.news_summary,
            key_companies=extraction.key_companies,
            derived_companies=[
                DerivedCompany(
                    ticker=d.ticker,
                    name=d.name,
                    derived_from=d.derived_from,
                    supply_relation=d.supply_relation,
                    market_sentiment=d.market_sentiment,
                    prediction=d.prediction,
                    rationale=d.rationale,
                    evidence_sources=self._to_evidence_sources(d.ticker, vector_context),
                )
                for d in llm_derived
            ],
        )

        await self._response_repo.save(news_id, response)
        await self._trigger_post_response_embedding(news)

        return response

    async def _find_derived_candidates(self, key_companies: list[KeyCompany]) -> list[DerivedCompanyCandidate]:
        # 온톨로지(ontology_client)가 아직 없어서 항상 빈 리스트 - 온톨로지 파트
        # 작업 완료 후 Neo4j 공급망 그래프 순회 결과로 교체.
        return []

    async def _collect_evidence(
        self,
        derived_candidates: list[DerivedCompanyCandidate],
        key_companies: list[KeyCompany],
    ) -> list[dict]:
        evidence: list[dict] = []
        for candidate in derived_candidates:
            for key_company in key_companies:
                evidence.extend(await self._vector_repo.find_mentions(candidate.ticker, key_company.name))
        return evidence

    @staticmethod
    def _to_evidence_sources(ticker: str, vector_context: list[dict]) -> list[EvidenceSource]:
        return [
            EvidenceSource(
                source_type=c["source_type"],
                title=c["title"],
                url=c["url"],
                published_date=c["published_date"],
                excerpt=c["text"][:200],
            )
            for c in vector_context
            if c["ticker"] == ticker
        ]

    @staticmethod
    async def _trigger_post_response_embedding(news: NewsRecord) -> None:
        # services/ingestion_service.py(임베딩 파트 작업)가 아직 없어서 no-op.
        # 실패해도 분석 응답 자체엔 영향 없어야 하므로 예외를 던지지 않는다.
        logger.info("사후 임베딩 미구현 - news_id=%s 건너뜀", news.news_id)
