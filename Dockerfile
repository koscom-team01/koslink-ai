# ==========================================
# kosLINK AI 통합 FastAPI & RAG 엔진 Dockerfile
# ==========================================
FROM python:3.11-slim-bookworm

# 작업 디렉토리 설정
WORKDIR /app

# 공식 PyPI 단일화, 타임아웃 300초, 리트라이 20회 설정 (네트워크 타임아웃 완벽 차단)
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=20 \
    PIP_INDEX_URL=https://pypi.org/simple

# 단일 통합 requirements.txt 및 shared 모듈 복사
COPY requirements.txt /app/requirements.txt
COPY shared /app/shared
COPY shared /shared

# 1. 고정 버전 의존성 패키지 일괄 설치
# 2. shared (dart-client) 패키지는 이미 설치된 의존성을 활용해 빌드 격리 없이(--no-build-isolation) 설치
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir --no-deps --no-build-isolation /app/shared

# 소스 코드 복사
COPY rag /app/rag
COPY ontology /app/ontology

# Python 경로 설정
ENV PYTHONPATH="/app/rag:/app"

# 기본 환경변수 설정
ENV PORT=8000 \
    PG_CONNECTION_STRING="postgresql+psycopg://admin:adminpassword@localhost:5432/koscomdb" \
    NEO4J_URI="bolt://localhost:7687" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="neo4jpassword"

EXPOSE 8000

# FastAPI 서버 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
