"""kosLINK AI - 온톨로지(Neo4j) 조회 인터페이스.

RAG 서버가 Neo4j 그래프에 직접 Cypher를 짜지 않고 이 모듈의 함수만 호출해
핵심 종목과 연관된 종목(하드 팩트) 및 그래프 시각화용 노드/엣지를 가져올 수
있게 하는 창구.
docs/rag_architecture.md 4장/7장 참고.
"""

import logging
from functools import lru_cache

from neo4j import AsyncDriver, AsyncGraphDatabase
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

# 기준 종목(ticker)에서 몇 hop까지 온톨로지 그래프를 탐색할지. related_stocks/
# graph 둘 다 이 값을 쓴다 - 호출자가 조절할 필요가 없어 함수 파라미터로 노출하지
# 않는다.
_MAX_HOP = 2

# related_stocks(=derived_candidates) 상한. 밀집 종목은 2-hop만으로 20개대까지
# 나와서 그대로 두면 후보마다 도는 RAG 근거 수집(임베딩 API 호출)과
# synthesize_related_stocks 프롬프트가 그만큼 커져 지연/비용이 늘어난다. 메인
# 기업 1개당 파생기업은 최대 4개까지만 보여준다. related_stocks는 1-hop을 먼저
# 채우고 2-hop을 이어붙이는 순서로 만들어지므로, 자르면 항상 가까운 관계부터 남는다.
_MAX_RELATED_CANDIDATES = 4

# Query A: 기준 종목에서 _MAX_HOP 이내에 있는 모든 노드를 찾는다 (자기 자신 제외).
_FIND_NODES_QUERY = """
MATCH (source:Stock {ticker: $ticker})
OPTIONAL MATCH (source)-[:SUPPLY_TO|RELATED_TO*1..%d]-(n:Stock)
WHERE n <> source
RETURN source, collect(DISTINCT n) AS neighbors
""" % _MAX_HOP

# Query B: 위에서 찾은 노드 집합 안에 실제로 존재하는 모든 엣지를 방향 그대로
# 가져온다. 방향성 패턴(->)이라 Cypher가 각 관계를 정확히 한 번만 매칭하므로,
# 예전 무방향 쿼리에서 쓰던 ticker_is_source 같은 방향 보정용 필드가 필요 없다.
_FIND_EDGES_QUERY = """
MATCH (a:Stock)-[rel:SUPPLY_TO|RELATED_TO]->(b:Stock)
WHERE a.id IN $node_ids AND b.id IN $node_ids
RETURN a.id AS source_id, b.id AS target_id, type(rel) AS edge_type,
       rel.relation_type AS sub_type, rel.product AS product,
       rel.productCategory AS product_category
"""

# 그래프 시각화 UI에서 엣지 라벨로 쓸 짧은 한국어 표기. relation_type(RELATED_TO)과
# SUPPLY_TO 둘 다 포함한다. _to_label이 이 딕셔너리에 없는 키는 원본 영문 그대로
# 반환해서, 실제 Neo4j 데이터의 relation_type 전체 목록(MATCH ()-[rel:RELATED_TO]->()
# RETURN DISTINCT rel.relation_type로 확인)과 반드시 맞춰둬야 응답에 영문이
# 새지 않는다.
_RELATION_LABELS = {
    "SUPPLY_TO": "공급계약",
    "SUPPLY_CHAIN": "공급망",
    "EQUITY_INVESTMENT": "지분투자",
    "AFFILIATE": "계열/관계사",
    "LICENSING": "기술라이선싱",
    "COMPETITOR": "경쟁사",
    "MNA": "인수합병",
    "OTHER": "기타관계",
    "TECH_COOPERATION": "기술협력",
    "MARKET_COMPETITION": "시장경쟁",
}


class RelatedStock(BaseModel):
    """기준 종목까지의 경로가 있는 연관 종목 카드 (related_stocks 리스트용)."""

    ticker: str
    name: str
    relation_label: str
    relation_path: str


class GraphNode(BaseModel):
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


class OntologyGraph(BaseModel):
    originId: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class OntologyExploreResult(BaseModel):
    """온톨로지 그래프 탐색 결과. related_stocks(카드 리스트)와 graph(시각화용
    노드/엣지)를 함께 담는다."""

    related_stocks: list[RelatedStock]
    graph: OntologyGraph


def _empty_result(ticker: str) -> OntologyExploreResult:
    return OntologyExploreResult(
        related_stocks=[],
        graph=OntologyGraph(originId=ticker, nodes=[], edges=[]),
    )


@lru_cache
def get_neo4j_driver() -> AsyncDriver:
    settings = get_settings()
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )


def _to_label(sub_type: str) -> str:
    return _RELATION_LABELS.get(sub_type, sub_type)


def _edge_label(edge_type: str, sub_type: str | None, product_category: str | None) -> str:
    if edge_type == "RELATED_TO":
        return _to_label(sub_type)
    # productCategory는 pipeline_updater.py의 공급계약 추출 LLM이 직접 산출하는
    # 투자자 친화적 카테고리(예: "테스트 장비 공급"). 없는 엣지(과거 데이터 등)는
    # 범용 라벨로 폴백한다.
    return product_category or _RELATION_LABELS["SUPPLY_TO"]


async def find_related_companies(ticker: str) -> OntologyExploreResult:
    """기준 종목(ticker)에서 2-hop 이내 온톨로지 그래프를 조회한다.

    Neo4j 연결/쿼리 실패 시 예외를 던지지 않고 빈 값으로 폴백한다
    (docs/rag_architecture.md 7장 "[2] 온톨로지 조회" 스펙).
    """
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            node_result = await session.run(_FIND_NODES_QUERY, ticker=ticker)
            node_record = await node_result.single()
            if node_record is None or node_record["source"] is None:
                return _empty_result(ticker)

            origin = node_record["source"]
            neighbors = [n for n in node_record["neighbors"] if n is not None]
            node_by_id = {origin["id"]: origin}
            for n in neighbors:
                node_by_id[n["id"]] = n

            edge_result = await session.run(_FIND_EDGES_QUERY, node_ids=list(node_by_id.keys()))
            edge_records = [record async for record in edge_result]
    except Exception:
        logger.warning("온톨로지 조회 실패 (ticker=%s) - 빈 값으로 폴백", ticker, exc_info=True)
        return _empty_result(ticker)

    origin_id = origin["id"]

    edges = [
        {
            "source_id": r["source_id"],
            "target_id": r["target_id"],
            "label": _edge_label(r["edge_type"], r["sub_type"], r["product_category"]),
        }
        for r in edge_records
    ]

    # related_stocks: 기준 종목부터의 경로(1-hop/2-hop)를 조립한다. 노드별 인접
    # 엣지 lookup을 양쪽 endpoint 기준으로 구성한다.
    adjacency: dict[str, list[dict]] = {}
    for e in edges:
        adjacency.setdefault(e["source_id"], []).append(e)
        adjacency.setdefault(e["target_id"], []).append(e)

    def other_side(edge: dict, node_id: str) -> str:
        return edge["target_id"] if edge["source_id"] == node_id else edge["source_id"]

    related_stocks: list[RelatedStock] = []
    # (endpoint_id, intermediate_id) - intermediate_id는 2-hop 항목의 경유 노드,
    # 1-hop 항목은 None. graph를 related_stocks와 같은 기준으로 자르기 위해 함께
    # 추적한다.
    related_node_ids: list[tuple[str, str | None]] = []
    hop1_ids: set[str] = set()

    for edge in adjacency.get(origin_id, []):
        other_id = other_side(edge, origin_id)
        other = node_by_id[other_id]
        hop1_ids.add(other_id)
        related_stocks.append(
            RelatedStock(
                ticker=other.get("ticker") or "",
                name=other["name"],
                relation_label=edge["label"],
                relation_path=f"{origin['name']} → {other['name']}",
            )
        )
        related_node_ids.append((other_id, None))

    for r_id in hop1_ids:
        r_node = node_by_id[r_id]
        for edge in adjacency.get(r_id, []):
            y_id = other_side(edge, r_id)
            # 원점으로 돌아가는 엣지, 그리고 이미 1-hop으로 직접 연결된 노드는
            # 더 긴 경로로 중복 표시하지 않는다.
            if y_id == origin_id or y_id in hop1_ids:
                continue
            y_node = node_by_id[y_id]
            related_stocks.append(
                RelatedStock(
                    ticker=y_node.get("ticker") or "",
                    name=y_node["name"],
                    relation_label=edge["label"],
                    relation_path=f"{origin['name']} → {r_node['name']} → {y_node['name']}",
                )
            )
            related_node_ids.append((y_id, r_id))

    # related_stocks가 카드로 노출하는 만큼만 graph도 보여준다 - 잘라내기 전엔
    # 카드는 4개인데 그래프는 2-hop 전체가 나와 화면과 그래프가 서로 다른
    # 이야기를 하는 문제가 있었다. 1-hop이 항상 2-hop보다 앞에 오는 조립 순서
    # (위 루프) 덕분에, 앞에서부터 자르기만 해도 2-hop 항목의 경유 노드
    # (intermediate_id)는 이미 그 앞의 1-hop 항목으로 포함돼 있어 그래프가
    # 끊기지 않는다.
    related_stocks = related_stocks[:_MAX_RELATED_CANDIDATES]
    related_node_ids = related_node_ids[:_MAX_RELATED_CANDIDATES]

    included_ids = {origin_id}
    for endpoint_id, intermediate_id in related_node_ids:
        included_ids.add(endpoint_id)
        if intermediate_id is not None:
            included_ids.add(intermediate_id)

    graph = OntologyGraph(
        originId=origin_id,
        nodes=[
            GraphNode(
                id=node["id"],
                name=node["name"],
                ticker=node.get("ticker") or "",
                marketType=node.get("marketType") or "",
                capSize=node.get("capSize") or "",
            )
            for node in node_by_id.values()
            if node["id"] in included_ids
        ],
        edges=[
            GraphEdge(id=f"e{i}", source=e["source_id"], target=e["target_id"], relation=e["label"])
            for i, e in enumerate(edges, start=1)
            if e["source_id"] in included_ids and e["target_id"] in included_ids
        ],
    )

    return OntologyExploreResult(related_stocks=related_stocks, graph=graph)
