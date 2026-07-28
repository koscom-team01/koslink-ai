# ==========================================
# kosLINK AI 통합 FastAPI & RAG 엔진 Dockerfile
# ==========================================
FROM python:3.11-slim-bookworm

# 작업 디렉토리 설정
WORKDIR /app

# ── pip 설정 ──────────────────────────────────────
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=5

# ── 빌드 도구 사전 설치 (PEP 517 격리 우회용) ────
RUN pip install --no-cache-dir setuptools>=68 wheel

# ── 의존성 설치 (소스 변경과 분리하여 Docker 캐시 활용) ──
COPY requirements.txt /app/requirements.txt
COPY shared /app/shared

# 1. requirements.txt로 모든 파이썬 의존성 일괄 설치
# 2. shared(dart-client) 패키지를 --no-build-isolation으로 설치
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir --no-build-isolation --no-deps /app/shared

# ── 소스 코드 복사 ────────────────────────────────
COPY rag /app/rag
COPY ontology /app/ontology

# Python 경로 설정
ENV PYTHONPATH="/app/rag:/app"

# ── 기본 환경변수 설정 ──────────────────────────────
ENV PORT=8000 \
    PG_CONNECTION_STRING="postgresql+psycopg://admin:adminpassword@localhost:5432/koscomdb" \
    NEO4J_URI="bolt://localhost:7687" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="neo4jpassword" \
    DART_CACHE_DIR=".cache/dart" \
    EMBEDDING_PROVIDER="openai" \
    EMBEDDING_MODEL_KURE="nlpai-lab/KURE-v1" \
    EMBEDDING_MODEL_BGE_M3="BAAI/bge-m3" \
    EMBEDDING_DEVICE="cpu" \
    VECTOR_COLLECTION_NAME="market_evidence"

EXPOSE 8000

# FastAPI 서버 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
