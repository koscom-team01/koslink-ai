"""kosLINK AI - RAG 서버 SQLAlchemy 비동기 엔진/세션.

PG_CONNECTION_STRING이 psycopg3(postgresql+psycopg://) DSN이라 동기/비동기
엔진 모두 같은 문자열을 그대로 쓸 수 있다.
"""

import asyncio
import sys
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

# psycopg3의 비동기 드라이버는 Windows 기본 이벤트 루프(ProactorEventLoop)를
# 지원하지 않는다 (Linux/Mac은 영향 없음) - 엔진 생성 전에 정책을 바꿔둔다.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

settings = get_settings()

engine = create_async_engine(settings.PG_CONNECTION_STRING)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
