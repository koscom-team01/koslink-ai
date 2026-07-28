"""kosLINK AI - ai_responses 테이블(뉴스별 분석 응답) 저장 리포지토리.

ai_responses는 news와 마찬가지로 app/db/base.py의 Declarative Base로 매핑하지
않고 SQLAlchemy Core로 직접 다룬다 (docs/rag_db_schema.md 1-5 참고).
"""

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.news_analysis import EvidenceDebugEntry, NewsAnalysisResponse


class ResponseRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def save(
        self,
        news_id: int,
        response: NewsAnalysisResponse,
        evidence_debug: list[EvidenceDebugEntry],
    ) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO ai_responses
                    (news_id, news_summary, source, origin_stocks, related_stocks, final_summary, graph, evidence_debug, status)
                VALUES
                    (:news_id, CAST(:news_summary AS jsonb), CAST(:source AS jsonb),
                     CAST(:origin_stocks AS jsonb), CAST(:related_stocks AS jsonb),
                     :final_summary, CAST(:graph AS jsonb), CAST(:evidence_debug AS jsonb), 'done')
                ON CONFLICT (news_id) DO UPDATE SET
                    news_summary = EXCLUDED.news_summary,
                    source = EXCLUDED.source,
                    origin_stocks = EXCLUDED.origin_stocks,
                    related_stocks = EXCLUDED.related_stocks,
                    final_summary = EXCLUDED.final_summary,
                    graph = EXCLUDED.graph,
                    evidence_debug = EXCLUDED.evidence_debug,
                    status = EXCLUDED.status,
                    error_message = NULL
                """
            ),
            {
                "news_id": news_id,
                "news_summary": json.dumps(response.news_summary),
                "source": response.source.model_dump_json(),
                "origin_stocks": json.dumps([c.model_dump() for c in response.origin_stocks]),
                "related_stocks": json.dumps([c.model_dump() for c in response.related_stocks]),
                "final_summary": response.final_summary,
                "graph": response.graph.model_dump_json(),
                "evidence_debug": json.dumps([e.model_dump() for e in evidence_debug]),
            },
        )
        await self._session.commit()

    async def save_failure(self, news_id: int, error_message: str) -> None:
        await self._session.execute(
            text(
                """
                INSERT INTO ai_responses (news_id, status, error_message)
                VALUES (:news_id, 'failed', :error_message)
                ON CONFLICT (news_id) DO UPDATE SET
                    status = 'failed',
                    error_message = EXCLUDED.error_message
                """
            ),
            {"news_id": news_id, "error_message": error_message},
        )
        await self._session.commit()
