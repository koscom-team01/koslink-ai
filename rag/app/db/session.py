"""kosLINK AI - RAG 서버 SQLAlchemy 비동기 엔진/세션.

PG_CONNECTION_STRING이 psycopg3(postgresql+psycopg://) DSN이라 동기/비동기
엔진 모두 같은 문자열을 그대로 쓸 수 있다.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.PG_CONNECTION_STRING)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
