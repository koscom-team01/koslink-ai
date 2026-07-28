"""kosLINK AI - news 테이블(백엔드 소유) 단건 조회 리포지토리.

news는 app/db/base.py의 Declarative Base로 매핑하지 않는다 - RAG 소유 테이블이
아니라 백엔드가 적재하는 테이블이라 SQLAlchemy Core로 직접 쿼리한다.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class NewsRecord:
    news_id: int
    title: str | None
    body: str | None
    press: str | None
    url: str | None
    published_at: datetime | None
    status: str


class NewsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, news_id: int) -> NewsRecord | None:
        result = await self._session.execute(
            text(
                """
                SELECT news_id, title, body, press, url, published_at, status
                FROM news
                WHERE news_id = :news_id
                """
            ),
            {"news_id": news_id},
        )
        row = result.mappings().first()
        if row is None:
            return None
        return NewsRecord(**row)

    async def mark_embedded(self, news_id: int) -> None:
        """사후 임베딩 완료 시각 기록 (rag_db_schema.md 1-4절 - RAG 쪽 책임 컬럼)."""
        await self._session.execute(
            text("UPDATE news SET rag_embedded_at = now() WHERE news_id = :news_id"),
            {"news_id": news_id},
        )
        await self._session.commit()
