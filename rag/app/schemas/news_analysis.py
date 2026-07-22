"""kosLINK AI - 뉴스 분석 응답 Pydantic 스키마.

docs/rag_architecture.md 7장 응답 스키마를 그대로 매핑한다. 요청은 body 없이
POST /api/v1/news/{news_id}/analyze의 경로 파라미터만 쓰므로 별도 모델이 없다.
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
