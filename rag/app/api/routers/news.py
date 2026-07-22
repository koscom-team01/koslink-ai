"""kosLINK AI - 뉴스 분석 API 라우터."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_retrieval_service
from app.schemas.news_analysis import NewsAnalysisResponse
from app.services.retrieval_service import NewsNotFoundError, RetrievalService

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.post("/{news_id}/analyze", response_model=NewsAnalysisResponse)
async def analyze_news(
    news_id: int,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
) -> NewsAnalysisResponse:
    try:
        return await service.analyze(news_id)
    except NewsNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
