# KURE-v1 임베딩 서버. Apple Silicon(arm64) 로컬 개발을 위해 michaelf34/infinity의
# 공식 이미지(amd64 전용) 대신, infinity-emb 파이썬 패키지를 arm64 네이티브 베이스 위에서 직접 빌드한다.
# python:3.11-slim은 멀티아키텍처 이미지라 arm64/amd64 모두에서 에뮬레이션 없이 그대로 빌드된다.
FROM python:3.11-slim

# click<8.3 / transformers<4.49 / optimum<2.0: infinity_emb가 최신 버전과 호환이 깨져
# 기동 자체가 실패하는 알려진 이슈들이라 버전을 고정한다 (michaelfeil/infinity#656).
RUN pip install --no-cache-dir "click<8.3" "transformers<4.49" "optimum<2.0" "infinity-emb[torch,server,optimum]"

ENV MODEL_ID=nlpai-lab/KURE-v1
ENV PORT=7997

EXPOSE 7997

# 모델은 이미지 빌드시가 아니라 컨테이너 최초 기동시 HuggingFace에서 다운로드되어
# /app/.cache 볼륨에 캐시된다 (docker-compose.yml 참고).
CMD ["sh", "-c", "infinity_emb v2 --model-id ${MODEL_ID} --port ${PORT}"]
