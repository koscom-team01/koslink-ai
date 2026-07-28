"""kosLINK AI - 뉴스 분석 응답 Pydantic 스키마.

docs/rag_architecture.md 7장 응답 스키마를 그대로 매핑한다. 요청 바디는 없다 -
POST /api/v1/news/analyze-pending는 쿼리 파라미터(limit)만 받고, 처리 대상
뉴스는 news.status='pending'을 직접 조회해서 서버가 정한다.

origin_stocks/related_stocks 이원화: origin_stocks는 뉴스에 실제로 언급된
핵심 기업(LLM이 companies 유니버스 안에서 직접 추출), related_stocks는
온톨로지 그래프로 찾은 파생/연관 기업이다 - 근거의 성격이 달라서(전자는 텍스트
추출, 후자는 그래프 순회 + RAG 근거) 나눈다.
"""

from typing import Literal

from pydantic import BaseModel

Direction = Literal["up", "down"]


class Source(BaseModel):
    """뉴스 원문 메타 정보 - news 테이블 컬럼을 응답 조립 시 그대로 옮겨 담는다."""

    press: str | None
    published_at: str | None
    url: str | None


class OriginStock(BaseModel):
    """뉴스가 실제로 다루고 있는 메인 기업 (companies 유니버스 안에서 LLM이 추출)."""

    ticker: str
    name: str
    status: Direction
    reason: str


class RelatedStock(BaseModel):
    """온톨로지로 찾은 파생/연관 기업.

    ticker/name/relation_label/relation_path는 온톨로지(ontology_client)가
    하드 팩트로 구성해 넘겨준다 - RAG는 그 위에 status/propagation만 LLM으로
    채운다 (retrieval_service._analyze 참고).
    """

    ticker: str
    name: str
    status: Direction
    relation_label: str
    relation_path: str
    propagation: str


class EvidenceSnippet(BaseModel):
    """related_stock 하나에 실제로 검색된 근거 청크 1건 - evidence_debug 전용."""

    source_type: Literal["disclosure", "report", "news"]
    title: str
    published_date: str
    excerpt: str


class EvidenceDebugEntry(BaseModel):
    """related_stock별 근거 판단 디버그 정보 - RAG 적중률 분석용으로 ai_responses의
    별도 컬럼(evidence_debug)에만 저장되고 NewsAnalysisResponse(FE 응답 계약)에는
    포함되지 않는다. evidence_source는 LLM이 propagation을 쓸 때 실제 RAG 근거를
    참고했는지(rag) 근거가 부족해 자체 추론했는지(inferred) 자가 판단한 값이고,
    retrieved_evidence는 그 판단과 무관하게 벡터검색에서 실제로 찾힌 청크 전부다 -
    "LLM이 근거를 썼다고 한 것"과 "실제로 검색된 것"을 분리해서 봐야 사람이
    사후에 검색 품질 자체를 검수할 수 있다."""

    ticker: str
    name: str
    evidence_source: Literal["rag", "inferred"]
    retrieved_evidence: list[EvidenceSnippet] = []


class GraphNode(BaseModel):
    """그래프 시각화용 노드 - ontology_client.OntologyExploreResult.graph.nodes를
    그대로 패싱한다 (필드 구성은 온톨로지 쪽 계약을 그대로 따름)."""

    id: str
    name: str
    ticker: str
    marketType: str
    capSize: str


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str


class Graph(BaseModel):
    """그래프 시각화용 데이터. originId/nodes/edges는 온톨로지의
    OntologyExploreResult.graph를 그대로 패싱하고(origin_stocks가 여럿이면
    ticker별 조회 결과를 합침), newsId만 RAG가 조립 시 채워 넣는다."""

    newsId: str
    originId: str
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []


class NewsAnalysisResponse(BaseModel):
    news_summary: list[str]
    source: Source
    origin_stocks: list[OriginStock] = []
    related_stocks: list[RelatedStock] = []
    final_summary: str
    graph: Graph


class PendingAnalysisResult(BaseModel):
    """POST /api/v1/news/analyze-pending 배치 처리 결과 - 뉴스 1건당 성공/실패."""

    news_id: int
    status: Literal["done", "failed"]
    error: str | None = None
