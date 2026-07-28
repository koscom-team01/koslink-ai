"""kosLINK AI - RAG 서버 FastAPI 엔트리포인트.

로컬(Windows) 실행은 `uvicorn app.main:app` 대신 `python -m app.main`을 쓴다.
uvicorn은 Windows에서 `asyncio.set_event_loop_policy()`를 아예 참조하지 않고
`asyncio.ProactorEventLoop`를 루프 팩토리로 하드코딩해버린다
(uvicorn/loops/asyncio.py의 asyncio_loop_factory) - 그래서 db/session.py의
정책 변경이 uvicorn.run()에는 안 먹힌다(psycopg 비동기 드라이버가
ProactorEventLoop에서 즉시 실패). 그래서 uvicorn.run()에 맡기지 않고, 여기서
직접 SelectorEventLoop를 만들어 그 위에 server.serve()를 올린다.

배포(Linux/Docker)는 이 문제 자체가 없으므로 평소처럼 `uvicorn app.main:app`
그대로 쓰면 된다 - 이 우회는 로컬 Windows 개발 전용.
"""

import asyncio
import logging
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers.news import router as news_router
from app.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(title="kosLINK AI - RAG Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://koslink-ai.hwangonjang.com",
        "http://koslink-ai.hwangonjang.com",
        "https://koslink.hwangonjang.com",
        "http://koslink.hwangonjang.com",
        "http://localhost:5173",
        "http://localhost:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(news_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "message": "kosLINK AI Server is running"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}



async def _serve() -> None:
    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=get_settings().PORT)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_serve())
    else:
        asyncio.run(_serve())
