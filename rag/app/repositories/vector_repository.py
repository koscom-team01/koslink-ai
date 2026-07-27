"""kosLINK AI - pgvector(langchain_pg_embedding)에서 파생기업 근거를 찾는 리포지토리.

근거는 두 종류로 나눈다.
1. find_mentions: derived 기업 자신의 청크 안에 key 기업 이름이 실제로 언급된
   청크를 찾는다 - 임베딩 없이 키워드 매칭(ILIKE)만으로 되는, 가장 확실한 직접 근거.
2. similarity_search: 뉴스 요약과 derived 기업 청크 간 의미적 유사도로 찾는
   간접 근거. PGVector.asimilarity_search에 ticker 필터를 걸어 그 기업 청크
   범위 안에서만 top-k를 가져온다.
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services.ingestion_service import build_async_vector_store


class VectorRepository:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._collection_name = get_settings().VECTOR_COLLECTION_NAME

    async def find_mentions(self, ticker: str, keyword: str, k: int = 5) -> list[dict]:
        result = await self._session.execute(
            text(
                """
                SELECT
                    e.cmetadata->>'ticker' AS ticker,
                    e.cmetadata->>'source_type' AS source_type,
                    e.cmetadata->>'title' AS title,
                    e.cmetadata->>'url' AS url,
                    e.cmetadata->>'published_date' AS published_date,
                    e.document AS text
                FROM langchain_pg_embedding e
                JOIN langchain_pg_collection c ON c.uuid = e.collection_id
                WHERE c.name = :collection_name
                  AND e.cmetadata->>'ticker' = :ticker
                  AND e.document ILIKE :pattern
                LIMIT :k
                """
            ),
            {
                "collection_name": self._collection_name,
                "ticker": ticker,
                "pattern": f"%{keyword}%",
                "k": k,
            },
        )
        return [dict(row) for row in result.mappings().all()]

    async def similarity_search(self, ticker: str, query: str, k: int = 5) -> list[dict]:
        vector_store = build_async_vector_store()
        results = await vector_store.asimilarity_search(query, k=k, filter={"ticker": ticker})
        return [
            {
                "ticker": r.metadata.get("ticker"),
                "source_type": r.metadata.get("source_type"),
                "title": r.metadata.get("title"),
                "url": r.metadata.get("url"),
                "published_date": r.metadata.get("published_date"),
                "text": r.page_content,
            }
            for r in results
        ]
