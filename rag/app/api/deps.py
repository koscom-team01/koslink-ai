"""kosLINK AI - API 의존성 주입."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.retrieval_service import RetrievalService


async def get_retrieval_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RetrievalService:
    return RetrievalService(session)
