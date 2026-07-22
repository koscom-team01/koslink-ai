"""kosLINK AI - RAG 서버 FastAPI 엔트리포인트."""

from fastapi import FastAPI

app = FastAPI(title="kosLINK AI - RAG Server")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
