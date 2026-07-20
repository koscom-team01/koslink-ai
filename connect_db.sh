#!/bin/bash
# ==============================================================================
# 개발자 로컬 DB 터널링 접속 스크립트 (Port-Forwarding)
# ==============================================================================

# 색상 정의
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
YELLOW='\033[1;33m'

KUBECONFIG_FILE="team1-kubeconfig.yaml"

if [ ! -f "$KUBECONFIG_FILE" ]; then
    echo -e "${RED}[ERROR] '$KUBECONFIG_FILE' 파일을 찾을 수 없습니다.${NC}"
    echo -e "먼저 배포를 완료한 뒤, 해당 파일을 프로젝트 루트 디렉토리에 위치시키세요."
    exit 1
fi

export KUBECONFIG="$(pwd)/$KUBECONFIG_FILE"

echo -e "${GREEN}[INFO] RKE2 클러스터 원격 터널링(Port-Forward) 연결 중...${NC}"

# 기존 터널링 프로세스가 있으면 안전하게 사전 종료
pkill -f "port-forward svc/postgresql" || true
pkill -f "port-forward svc/neo4j" || true

# 1. PostgreSQL 터널링 실행 (백그라운드)
echo -e "${YELLOW}1. PostgreSQL 연결 중 (localhost:5432)...${NC}"
kubectl port-forward svc/postgresql 5432:5432 -n database &>/dev/null &
PG_PID=$!

# 2. Neo4j 터널링 실행 (백그라운드)
echo -e "${YELLOW}2. Neo4j 연결 중 (Browser: http://localhost:7474, Bolt: localhost:7687)...${NC}"
kubectl port-forward svc/neo4j 7474:7474 7687:7687 -n neo4j &>/dev/null &
NEO_PID=$!

sleep 3

# 프로세스 생존 여부 체크
if ps -p $PG_PID > /dev/null && ps -p $NEO_PID > /dev/null; then
    echo -e "\n${GREEN}======================================================================${NC}"
    echo -e "🎉 원격 데이터베이스 연결(Port-Forward) 터널이 정상 개방되었습니다!"
    echo -e "----------------------------------------------------------------------"
    echo -e "💾 ${GREEN}PostgreSQL (RDB & VectorDB)${NC}:"
    echo -e "   - Host: localhost"
    echo -e "   - Port: 5432"
    echo -e "   - DB: koscomdb"
    echo -e "   - User/Password: admin / adminpassword"
    echo -e "----------------------------------------------------------------------"
    echo -e "📊 ${GREEN}Neo4j (GraphDB)${NC}:"
    echo -e "   - Bolt URI: bolt://localhost:7687"
    echo -e "   - Web Browser: http://localhost:7474"
    echo -e "   - User/Password: neo4j / neo4jpassword"
    echo -e "======================================================================${NC}"
    echo -e "${YELLOW}접속을 종료하려면 [Enter] 키를 누르세요...${NC}"
    read -r
    
    # 백그라운드 프로세스 정리
    kill $PG_PID
    kill $NEO_PID
    echo -e "${GREEN}[INFO] 데이터베이스 터널링이 종료되었습니다.${NC}"
else
    echo -e "${RED}[ERROR] 터널링 연결에 실패했습니다.${NC}"
    echo -e "클러스터 내의 postgres 및 neo4j 파드가 정상 실행 중인지 확인하세요."
    kill $PG_PID 2>/dev/null || true
    kill $NEO_PID 2>/dev/null || true
    exit 1
fi
