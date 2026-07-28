"""kosLINK AI - 뉴스 분석 API 라우터.

백엔드는 1분마다 이 엔드포인트만 호출한다 - 어떤 뉴스를 분석할지(news_id)는
AI 서버가 news.status='pending'을 직접 조회해서 정하므로, 백엔드는 뉴스별로
개별 호출을 만들 필요가 없다.
"""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from app.api.deps import get_retrieval_service
from app.schemas.news_analysis import PendingAnalysisResult
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/api/v1/news", tags=["news"])


@router.post("/analyze-pending", response_model=list[PendingAnalysisResult])
async def analyze_pending_news(
    background_tasks: BackgroundTasks,
    service: Annotated[RetrievalService, Depends(get_retrieval_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PendingAnalysisResult]:
    return await service.analyze_pending(limit, background_tasks)
