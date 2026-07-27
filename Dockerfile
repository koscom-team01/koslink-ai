# ==========================================
# kosLINK AI 통합 FastAPI & RAG 엔진 Dockerfile
# (최적화: 슬림 의존성 + 빌드 격리 우회 + HTTP 미러)
# ==========================================
FROM python:3.11-slim-bookworm

# 작업 디렉토리 설정
WORKDIR /app

# ── pip 설정 ──────────────────────────────────────
# 1. 타임아웃 & 리트라이를 충분히 설정
# 2. 카카오 미러(HTTP 80)를 사용하여 K8s NAT Gateway의 HTTPS/SSL 세션 타임아웃 방지
# 3. trusted-host 지정으로 HTTP 미러 허용
ENV PIP_DEFAULT_TIMEOUT=100 \
    PIP_RETRIES=10 \
    PIP_INDEX_URL=http://mirror.kakao.com/pypi/simple \
    PIP_TRUSTED_HOST=mirror.kakao.com

# ── 빌드 도구 사전 설치 (PEP 517 격리 우회용) ────
RUN pip install --no-cache-dir setuptools>=68 wheel

# ── 의존성 설치 (소스 변경과 분리하여 Docker 캐시 활용) ──
COPY requirements.txt /app/requirements.txt
COPY shared /app/shared

# 1. requirements.txt로 모든 파이썬 의존성 일괄 설치
# 2. shared(dart-client) 패키지를 --no-build-isolation으로 설치
#    → 이미 설치된 setuptools를 사용하므로 pypi.org 격리 환경 패키지 다운로드 불필요
RUN pip install --no-cache-dir -r /app/requirements.txt && \
    pip install --no-cache-dir --no-build-isolation --no-deps /app/shared

# ── 소스 코드 복사 ────────────────────────────────
COPY rag /app/rag
COPY ontology /app/ontology

# Python 경로 설정
ENV PYTHONPATH="/app/rag:/app"

# 기본 포트
ENV PORT=8000

EXPOSE 8000

# FastAPI 서버 실행
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
