# 빌드 컨텍스트는 반드시 저장소 루트여야 합니다 (ontology/requirements.txt의
# `-e ../shared`가 이미지 안에서도 풀리려면 shared/ 폴더가 함께 필요합니다):
#   docker build -f ontology/Dockerfile .
#
# 1. Base Image 설정 (경량화된 Python Slim 이미지 사용)
FROM python:3.11-slim

# 2. 컨테이너 내부 작업 디렉토리 지정
WORKDIR /app

# 3. shared/dart_client 먼저 복사 (requirements.txt의 -e ../shared가 참조하는 경로)
COPY shared /shared

# 4. 패키지 설치를 위한 requirements.txt 복사 및 의존성 설치
COPY ontology/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 실시간 파이프라인 수집 및 검증 스크립트 소스 복사
COPY ontology/config.py .
COPY ontology/initialize_ontology.py .
COPY ontology/update_graph.py .
COPY ontology/pipeline_updater.py .

# 6. 환경 변수 기본값 지정 (쿠버네티스 ConfigMap/Secret으로 재정의 가능)
ENV NEO4J_URI="bolt://localhost:7687" \
    NEO4J_USER="neo4j" \
    NEO4J_PASSWORD="password123" \
    ANTHROPIC_API_KEY="" \
    DART_API_KEY=""

# 7. 쿠버네티스 Job 기동 시 기본 실행 파일 지정 (원샷 배치 기동)
ENTRYPOINT ["python", "pipeline_updater.py"]
