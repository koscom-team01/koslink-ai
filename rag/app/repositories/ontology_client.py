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
_FIND_RELATED_QUERY = """
MATCH (source:Stock {ticker: $ticker})-[rel:SUPPLY_TO|RELATED_TO]-(related:Stock)
RETURN
    COALESCE(related.ticker, '') AS ticker,
    related.name AS name,
    type(rel) AS relation_type,
    rel.product AS product,
    rel.description AS description
"""


class RelatedCompanyFact(BaseModel):
    """온톨로지 그래프 순회로 찾은 연관 종목 하드 팩트."""

    ticker: str
    name: str
    derived_from: str
    supply_relation: str


@lru_cache
def get_neo4j_driver() -> AsyncDriver:
    settings = get_settings()
    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )


def _to_supply_relation(relation_type: str, product: str | None, description: str | None) -> str:
    if relation_type == "SUPPLY_TO":
        return f"공급관계 ({product})" if product else "공급관계"
    return description or relation_type


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

    return [
        RelatedCompanyFact(
            ticker=record["ticker"],
            name=record["name"],
            derived_from=ticker,
            supply_relation=_to_supply_relation(
                record["relation_type"], record["product"], record["description"]
            ),
        )
        for record in records
    ]
