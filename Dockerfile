# ==========================================
# kosLINK AI 통합 FastAPI & RAG 엔진 Dockerfile
# ==========================================
FROM python:3.11-slim-bookworm

# 작업 디렉토리 설정
WORKDIR /app

# 공통 shared 라이브러리 및 requirements 복사
COPY shared /shared
COPY shared /app/shared
COPY rag/requirements.txt /app/rag_requirements.txt
COPY ontology/requirements.txt /app/ontology_requirements.txt

# Python 경량 의존성 및 공통 shared 패키지 설치
RUN pip install --no-cache-dir -r /app/rag_requirements.txt && \
    pip install --no-cache-dir -r /app/ontology_requirements.txt && \
    pip install --no-cache-dir -e /app/shared

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
