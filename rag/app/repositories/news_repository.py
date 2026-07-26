"""kosLINK AI - news 테이블(백엔드 소유) 조회/상태 갱신 리포지토리.

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

    async def mark_embedded(self, news_id: int) -> None:
        """사후 임베딩 완료 시각 기록 (rag_db_schema.md 1-4절 - RAG 쪽 책임 컬럼)."""
        await self._session.execute(
            text("UPDATE news SET rag_embedded_at = now() WHERE news_id = :news_id"),
            {"news_id": news_id},
        )
        await self._session.commit()

    async def claim_pending(self, limit: int) -> list[NewsRecord]:
        """미응답(status='pending') 뉴스를 골라 'analyzing'으로 선점하며 반환한다.

        조회와 선점을 한 UPDATE...RETURNING으로 묶어야 한다 - 백엔드가 1분마다
        호출하는데 배치 처리가 1분을 넘기면 다음 호출과 겹칠 수 있어서, SELECT 후
        별도 UPDATE로 나누면 두 호출이 같은 pending 행을 동시에 집어갈 수 있다.
        FOR UPDATE SKIP LOCKED로 그 레이스를 원천 차단한다.
        """
        result = await self._session.execute(
            text(
                """
                UPDATE news
                SET status = 'analyzing'
                WHERE news_id IN (
                    SELECT news_id FROM news
                    WHERE status = 'pending'
                    ORDER BY published_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT :limit
                )
                RETURNING news_id, title, body, press, url, published_at, status
                """
            ),
            {"limit": limit},
        )
        rows = result.mappings().all()
        await self._session.commit()
        return [NewsRecord(**row) for row in rows]

    async def mark_done(self, news_id: int) -> None:
        await self._session.execute(
            text("UPDATE news SET status = 'done', analyzed_at = now() WHERE news_id = :news_id"),
            {"news_id": news_id},
        )
        await self._session.commit()

    async def mark_failed(self, news_id: int) -> None:
        await self._session.execute(
            text("UPDATE news SET status = 'failed' WHERE news_id = :news_id"),
            {"news_id": news_id},
        )
        await self._session.commit()
