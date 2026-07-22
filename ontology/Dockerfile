# 1. Base Image 설정 (경량화된 Python Slim 이미지 사용)
FROM python:3.11-slim

# 2. 컨테이너 내부 작업 디렉토리 지정
WORKDIR /app

# 3. 패키지 설치를 위한 requirements.txt 복사 및 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. 실시간 파이프라인 수집 및 검증 스크립트 소스 복사
COPY config.py .
COPY initialize_ontology.py .
COPY update_graph.py .
COPY pipeline_updater.py .
COPY test_api_extraction.py .

# 5. 환경 변수 기본값 지정 (쿠버네티스 ConfigMap/Secret으로 재정의 가능)
ENV NEO4J_URI="bolt://localhost:7687" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="password123" \
    ANTHROPIC_API_KEY="" \
    DART_API_KEY=""

# 6. 쿠버네티스 Job 기동 시 기본 실행 파일 지정 (원샷 배치 기동)
ENTRYPOINT ["python", "pipeline_updater.py"]
