"""kosLINK AI - ai_responses 테이블(뉴스별 분석 응답) 저장 리포지토리.

ai_responses는 news와 마찬가지로 app/db/base.py의 Declarative Base로 매핑하지
않고 SQLAlchemy Core로 직접 다룬다 (docs/rag_db_schema.md 1-5 참고).
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.news_analysis import NewsAnalysisResponse


class ResponseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(self, news_id: int, response: NewsAnalysisResponse) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO ai_responses
                    (news_id, news_summary, key_companies, derived_companies, status)
                VALUES
                    (:news_id, :news_summary, CAST(:key_companies AS jsonb), CAST(:derived_companies AS jsonb), 'done')
                ON CONFLICT (news_id) DO UPDATE SET
                    news_summary = EXCLUDED.news_summary,
                    key_companies = EXCLUDED.key_companies,
                    derived_companies = EXCLUDED.derived_companies,
                    status = EXCLUDED.status,
                    error_message = NULL
                """
            ),
            {
                "news_id": news_id,
                "news_summary": response.news_summary,
                "key_companies": json.dumps([c.model_dump() for c in response.key_companies]),
                "derived_companies": json.dumps([c.model_dump() for c in response.derived_companies]),
            },
        )
        await self._session.commit()
