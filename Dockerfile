# ==========================================
# kosLINK AI 통합 FastAPI & RAG 엔진 Dockerfile
# ==========================================
FROM python:3.11-slim

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 의존성 (필요 시 최소 패키지 설치)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && rm -rf /var/lib/apt-get/lists/*

# requirements.txt의 `-e ../shared` 상대경로 해소를 위해 /shared 및 /app/shared 복사
COPY shared /shared
COPY shared /app/shared
COPY rag/requirements.txt /app/rag_requirements.txt
COPY ontology/requirements.txt /app/ontology_requirements.txt

# Python 의존성 및 공통 shared 패키지 설치
RUN pip install --no-cache-dir -r /app/rag_requirements.txt && \
    pip install --no-cache-dir -r /app/ontology_requirements.txt && \
    pip install --no-cache-dir -e /app/shared

# 소스 코드 복사
COPY rag /app/rag
COPY ontology /app/ontology

# Python 경로 설정 (rag/ 하위 모듈이 app.main 등으로 정상 import 가능하도록 설정)
ENV PYTHONPATH="/app/rag:/app"

# 기본 환경변수 설정 (로컬 Docker 실행 시 fallback용, K8s 환경에서 Override 처리)
ENV PORT=8000 \
    PG_CONNECTION_STRING="postgresql+psycopg://admin:adminpassword@localhost:5432/koscomdb" \
    NEO4J_URI="bolt://localhost:7687" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="neo4jpassword"

EXPOSE 8000

# FastAPI 서버 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
