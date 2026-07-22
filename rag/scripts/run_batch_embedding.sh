#!/bin/bash
# ==============================================================================
# kosLINK AI - RAG 배치 임베딩 파이프라인 실행 스크립트
# KURE-v1 임베딩 서버 + Langflow를 띄우고, koslink_batch_embedding 플로우를
# GUI 없이 CLI로 실행한 뒤 실제로 임베딩 요청이 성공했는지까지 확인한다.
#
# 실행:
#   cd rag
#   ./scripts/run_batch_embedding.sh
# ==============================================================================

set -u

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

FLOW_PATH="/app/flows/koslink_batch_embedding.json"
HEALTH_TIMEOUT=300  # 임베딩 서버 최초 기동 시 모델 다운로드+최적화로 수 분 걸릴 수 있음

wait_for_health() {
    local name="$1"
    local url="$2"
    local elapsed=0

    echo -e "${YELLOW}   ${name} 기동 대기 중...${NC}"
    while ! curl -sf "$url" >/dev/null 2>&1; do
        sleep 5
        elapsed=$((elapsed + 5))
        if [ "$elapsed" -ge "$HEALTH_TIMEOUT" ]; then
            echo -e "${RED}   ❌ ${name}이 ${HEALTH_TIMEOUT}초 안에 기동되지 않았습니다.${NC}"
            echo "   docker compose logs ${name}로 원인을 확인하세요."
            return 1
        fi
    done
    echo -e "${GREEN}   ✅ ${name} 준비 완료 (${elapsed}초 소요)${NC}"
    return 0
}

echo -e "${GREEN}[1/4] 컨테이너 기동...${NC}"
docker compose up -d

echo -e "${GREEN}[2/4] 헬스체크...${NC}"
wait_for_health "embedding-server" "http://localhost:7997/health" || exit 1
wait_for_health "langflow" "http://localhost:7860/health" || exit 1

echo -e "${GREEN}[3/4] 배치 임베딩 플로우 실행...${NC}"
docker compose exec langflow langflow lfx run "$FLOW_PATH" -v

echo -e "${GREEN}[4/4] 임베딩 서버에 실제 요청이 도달했는지 확인...${NC}"
if docker compose logs embedding-server --tail 10 | grep -q 'POST /embeddings HTTP/1.1" 200 OK'; then
    echo -e "\n${GREEN}======================================================================${NC}"
    echo -e "${GREEN}🎉 배치 임베딩 파이프라인이 정상적으로 실행되었습니다.${NC}"
    echo -e "   DBeaver 등으로 langchain_pg_embedding 테이블에서 결과를 확인하세요."
    echo -e "${GREEN}======================================================================${NC}"
    exit 0
else
    echo -e "\n${RED}======================================================================${NC}"
    echo -e "${RED}❌ 임베딩 서버에서 성공 응답(200 OK)을 확인하지 못했습니다.${NC}"
    echo -e "   docker compose logs embedding-server 로 자세한 원인을 확인하세요."
    echo -e "${RED}======================================================================${NC}"
    exit 1
fi
