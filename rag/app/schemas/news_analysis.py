"""kosLINK AI - 뉴스 분석 응답 Pydantic 스키마.

docs/rag_architecture.md 7장 응답 스키마를 그대로 매핑한다. 요청 바디는 없다 -
POST /api/v1/news/analyze-pending는 쿼리 파라미터(limit)만 받고, 처리 대상
뉴스는 news.status='pending'을 직접 조회해서 서버가 정한다.
"""

from typing import Literal

from pydantic import BaseModel


class KeyCompany(BaseModel):
    ticker: str
    name: str


class EvidenceSource(BaseModel):
    source_type: Literal["disclosure", "report", "news"]
    title: str
    url: str
    published_date: str
    excerpt: str


class DerivedCompany(BaseModel):
    ticker: str
    name: str
    derived_from: str
    supply_relation: str
    market_sentiment: Literal["긍정적", "중립적", "부정적"]
    prediction: Literal["상승세", "보합", "하락세"]
    rationale: str
    evidence_sources: list[EvidenceSource] = []


class NewsAnalysisResponse(BaseModel):
    news_summary: str
    key_companies: list[KeyCompany] = []
    derived_companies: list[DerivedCompany] = []


class PendingAnalysisResult(BaseModel):
    """POST /api/v1/news/analyze-pending 배치 처리 결과 - 뉴스 1건당 성공/실패."""

    news_id: int
    status: Literal["done", "failed"]
    error: str | None = None
