# ==========================================
# kosLINK Ontology 배치 파이프라인 Dockerfile
# 빌드 컨텍스트: 저장소 루트 (docker build -f ontology/Dockerfile .)
# ==========================================
FROM python:3.11-slim

WORKDIR /app

# ── pip 설정 (카카오 HTTP 미러 + 타임아웃) ──
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=http://mirror.kakao.com/pypi/simple \
    PIP_TRUSTED_HOST=mirror.kakao.com

# ── 빌드 도구 사전 설치 (PEP 517 격리 우회용) ──
RUN pip install --no-cache-dir setuptools>=68 wheel

# ── shared/dart_client 패키지 설치 ──
COPY shared /app/shared
RUN pip install --no-cache-dir --no-build-isolation --no-deps /app/shared

# ── ontology 의존성 설치 ──
COPY ontology/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── 소스 코드 복사 ──
COPY ontology/config.py .
COPY ontology/initialize_ontology.py .
COPY ontology/update_graph.py .
COPY ontology/pipeline_updater.py .

# ── 환경 변수 기본값 (K8s ConfigMap/Secret으로 재정의 가능) ──
ENV NEO4J_URI="bolt://localhost:7687" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="password123" \
    ANTHROPIC_API_KEY="" \
    DART_API_KEY=""

# 쿠버네티스 Job 기동 시 기본 실행 파일
ENTRYPOINT ["python", "pipeline_updater.py"]
