"""kosLINK AI - 온톨로지(Neo4j) 조회 인터페이스.

RAG 서버가 Neo4j 그래프에 직접 Cypher를 짜지 않고 이 모듈의 함수만 호출해
핵심 종목과 연관된 종목(하드 팩트)을 가져올 수 있게 하는 창구.
docs/rag_architecture.md 4장/7장 참고.
"""

import logging
from functools import lru_cache

from neo4j import AsyncDriver, AsyncGraphDatabase
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

# 그래프 상 두 관계 타입 모두 조회한다: SUPPLY_TO(공급/거래, product 속성),
# RELATED_TO(지분투자/계열/라이선싱/경쟁/M&A, description 속성).
# 방향에 관계없이(무방향 패턴) 1-hop만 조회한다 - 두 관계 모두 DART 공시로
# 검증된 Hard Fact라 신뢰도가 가장 높은 범위로 한정한다.
# source_name/ticker_is_source는 supply_relation을 조회 방향과 무관하게 조립하기
# 위한 필드다 - RELATED_TO는 relation_type만으로 방향의 의미를 신뢰할 수 없어서
# (예: EQUITY_INVESTMENT조차 실제 투자자가 반대쪽인 사례가 있다) 양쪽 회사명을
# 항상 같이 보여주고, SUPPLY_TO는 스키마상 공급사→수요처 방향이 보장되므로
# ticker_is_source로 어느 쪽이 공급사인지만 판별한다.
_FIND_RELATED_QUERY = """
MATCH (source:Stock {ticker: $ticker})-[rel:SUPPLY_TO|RELATED_TO]-(related:Stock)
RETURN
    COALESCE(related.ticker, '') AS ticker,
    related.name AS name,
    source.name AS source_name,
    type(rel) AS edge_type,
    rel.relation_type AS sub_type,
    rel.product AS product,
    rel.description AS description,
    startNode(rel) = source AS ticker_is_source
"""

# 그래프 시각화 UI에서 엣지 라벨로 쓸 짧은 한국어 표기. relation_type(RELATED_TO)과
# SUPPLY_TO 둘 다 포함한다.
_RELATION_LABELS = {
    "SUPPLY_TO": "공급계약",
    "EQUITY_INVESTMENT": "지분투자",
    "AFFILIATE": "계열/관계사",
    "LICENSING": "기술라이선싱",
    "COMPETITOR": "경쟁사",
    "MNA": "인수합병",
    "OTHER": "기타관계",
}


class RelatedCompanyFact(BaseModel):
    """온톨로지 그래프 순회로 찾은 연관 종목 하드 팩트."""

    ticker: str
    name: str
    derived_from: str
    supply_relation: str
    label: str


@lru_cache
def get_neo4j_driver() -> AsyncDriver:
    settings = get_settings()
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )


def _to_label(relation_type: str) -> str:
    return _RELATION_LABELS.get(relation_type, relation_type)


def _to_supply_relation(
    edge_type: str,
    product: str | None,
    description: str | None,
    source_name: str,
    related_name: str,
    ticker_is_source: bool,
    label: str,
) -> str:
    """조회 기준(ticker)이 관계의 어느 쪽이든 동일하게 읽히도록, 항상 양쪽
    회사명과 관계 라벨을 함께 명시한다 (relation_type만으로는 방향의 의미를
    신뢰할 수 없어 한쪽을 문법적 주어로 강제하지 않는다)."""
    if edge_type == "SUPPLY_TO":
        supplier, buyer = (source_name, related_name) if ticker_is_source else (related_name, source_name)
        detail = f"{product} 공급" if product else "공급"
        return f"{supplier} → {buyer} ({label}): {detail}"

    detail = description or edge_type
    return f"{source_name} ↔ {related_name} ({label}): {detail}"


async def find_related_companies(ticker: str, hop: int = 1) -> list[RelatedCompanyFact]:
    """핵심 종목(ticker)과 1-hop 연관된 종목들을 하드 팩트로 반환한다.

    Neo4j 연결/쿼리 실패 시 예외를 던지지 않고 빈 리스트로 폴백한다
    (docs/rag_architecture.md 7장 "[2] 온톨로지 조회" 스펙).
    """
    if hop != 1:
        raise NotImplementedError("멀티홉(hop != 1)은 아직 지원하지 않습니다.")

    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            result = await session.run(_FIND_RELATED_QUERY, ticker=ticker)
            records = [record async for record in result]
    except Exception:
        logger.warning("온톨로지 조회 실패 (ticker=%s) - 빈 리스트로 폴백", ticker, exc_info=True)
        return []

    facts = []
    for record in records:
        edge_type = record["edge_type"]
        # SUPPLY_TO 엣지엔 relation_type 속성이 없다 - edge_type(SUPPLY_TO) 자체를
        # 라벨 키로 쓰고, RELATED_TO는 세부 분류(sub_type: COMPETITOR 등)를 쓴다.
        label = _to_label(record["sub_type"] if edge_type == "RELATED_TO" else edge_type)
        facts.append(
            RelatedCompanyFact(
                ticker=record["ticker"],
                name=record["name"],
                derived_from=ticker,
                supply_relation=_to_supply_relation(
                    edge_type,
                    record["product"],
                    record["description"],
                    record["source_name"],
                    record["name"],
                    record["ticker_is_source"],
                    label,
                ),
                label=label,
            )
        )
    return facts
