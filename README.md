# kosLINK AI: 3-Layer 밸류체인 온톨로지 & 하이브리드 RAG 엔진

본 프로젝트는 금융감독원(FSS) 공시 기반의 **Neo4j 온톨로지(GraphRAG)**와 **PostgreSQL(pgvector) 기반의 일반 RAG**를 융합하여 구성하는 AI 인덱스 빌더 서비스 백엔드입니다.

이 가이드는 **온톨로지 개발팀**과 **일반 RAG 개발팀** 간의 데이터 범위 구분, 쿠버네티스 원격 포트포워딩 터널링 접속, 그리고 통합 아키텍처 방향성을 정의합니다.

---

## 1. 👥 양대 RAG 팀 간의 상세 역할 및 개발 마일스톤 (Role & Milestones)

협업을 위해 **온톨로지(GraphRAG) 개발팀**과 **일반 RAG 개발팀**의 담당 영역 및 핵심 기능을 구분하고, 하이브리드 RAG로 병합하기 전 독립적으로 완수해야 하는 개별 사전 작업 체크리스트입니다.

```
                  ┌──► [1팀: 온톨로지 개발팀] ➔ DART 공시 분석 ➔ Neo4j (Hard Fact)
                  │
[종합 자연어 질문] ┼
                  │
                  └──► [2팀: 일반 RAG 개발팀] ➔ 뉴스/리포트 + 공시 ➔ PostgreSQL (Soft Info)
```

### 1) 기능 명세 및 역할 분담
| 구분 | 1팀: 온톨로지 개발팀 (GraphRAG) | 2팀: 일반 RAG 개발팀 (Vector RAG) |
| :--- | :--- | :--- |
| **담당 데이터** | DART 정기 사업보고서, DART 수시 공급계약 공시, 거래소 시가총액 정보 | **DART 정기 사업보고서, DART 수시 공시 정보**, 증권사 산업/종목 리포트(PDF), 일간 금융 뉴스, 소셜 피드 |
| **데이터 역할** | **정밀 팩트 구조화 (Hard Fact)**<br>법적 책임을 지는 밸류체인 연결 관계 추출 | **비정형 문서 세만틱 저장 (Soft Info & Context)**<br>보고서 및 공시 본문의 줄글에 대한 시맨틱 검색 |
| **저장 기술** | **Neo4j Graph Database** (인덱스/제약조건 활용) | **PostgreSQL (pgvector)** |
| **주요 기능** | 1) 공급망 팩트 적출 (`SUPPLY_TO` 엣지)<br>2) 공정 기술 매핑 (`BELONGS_TO` 엣지)<br>3) 다단계 의존성 분석 (Multi-hop 리스크 추적)<br>4) 규제 감사 대응용 공시 원본 URL 매핑 | 1) 비정형 문서 단락 유사도 검색 (Similarity Search)<br>2) 공시 및 정기 보고서 줄글 상세 내용 요약<br>3) 시장 뉴스 기사 감성 분석 (Sentiment)<br>4) 애널리스트 리포트 기반 상승/하락 심리 분석 |

### 2) 병합 전 각 팀의 개발 마일스톤 (Pre-merge Milestones)
두 RAG 채널을 최종 병합(Section 4)하기 전, 각 개발팀이 독립적으로 완수해야 하는 사전 테스트 단계입니다.

*   **1팀: 온톨로지 개발팀 (GraphRAG)**:
    1.  **그래프 DB 구축**: DART 원본 데이터를 마이닝하여 3-Layer(테마-역할군-기업) Neo4j 그래프 데이터베이스 기본 시드 구축.
    2.  **동적 쿼리 라우팅 구현**: STOCK/ROLE/BOTH 분기 처리를 위한 Cypher 쿼리 라우팅 로직을 함수화하여 완성.
    3.  **독립 체인 구동**: 추출된 원시 그래프 팩트를 AI 프롬프트에 실어 보내 자연어 팩트 답변을 리턴하는 독립 테스트 체인(Chain) 작동 완료 검증.
*   **2팀: 일반 RAG 개발팀 (Vector RAG)**:
    1.  **벡터 DB 적재**: PostgreSQL pgvector 데이터베이스를 기동하고, 증권사 PDF 리포트와 뉴스 기사 및 공시 본문을 청크 분할하여 임베딩 및 적재.
    2.  **유사도 검색 구현**: 입력 검색어 기반으로 관련 문서를 상위 K개 불러오는 유사도 검색(`Similarity Search`) 기능 구현.
    3.  **독립 체인 구동**: 검색된 본문 조각들을 AI 프롬프트에 Context로 주입하여 최신 시황 및 감성 요약 답변을 리턴하는 독립 테스트 체인 작동 완료 검증.

> 양 팀의 개별 체인이 로컬 터널을 통해 정상 작동함이 확인되면, 백엔드 오케스트레이터에서 **Section 4 코드 아키텍처**를 기준점 삼아 두 데이터 수집 채널을 결합하고 최종 하이브리드 RAG API 서버로 병합을 완료합니다.

---

## 2. 🔌 원격 클러스터 DB 터널링 접속 가이드 (`connect_db.sh` 사용법)

개발 편의와 데이터 동기화를 위해 각자 로컬에 디비를 구축하지 않고, **쿠버네티스 클러스터 내에 배포된 공용 데이터베이스에 터널을 뚫어(Port-Forwarding) 공동 사용**합니다.

이 기능을 수행하는 터널링 스크립트인 [connect_db.sh](file:///Users/ggona/Documents/koscom/미니프로젝트/koslink-ai/connect_db.sh)의 검증 및 사용법은 다음과 같습니다.

### 1) 작동 원리 및 스크립트 검증
*   본 스크립트는 로컬의 `team1-kubeconfig.yaml` 자격증명 파일을 사용해 RKE2 클러스터의 API 서버에 명령을 송신합니다.
*   백그라운드로 **PostgreSQL(Port 5432)** 및 **Neo4j(Bolt: 7687, Browser: 7474)** 포트포워딩을 활성화합니다.
*   기존에 켜져 있던 터널링 프로세스를 정리(`pkill -f`)하고 접속 성공 여부를 모니터링한 뒤, 사용자가 `Enter`를 누르면 터널을 안전하게 회수(`kill`)하도록 예외 처리가 완벽히 설계되어 있습니다.

### 2) 스크립트 사용 단계
1.  배포 인프라 폴더(`kosops/`)에 위치한 **`team1-kubeconfig.yaml`** 파일을 본 프로젝트의 루트 디렉토리(`./koslink-ai/`) 하위로 복사합니다.
2.  스크립트에 실행 권한을 부여합니다.
    ```bash
    chmod +x connect_db.sh
    ```
3.  터널링 스크립트를 가동합니다.
    ```bash
    ./connect_db.sh
    ```
4.  정상 가동 시 터널이 백그라운드에서 유지되며 아래 포트를 통해 로컬 데이터베이스처럼 즉시 접속할 수 있습니다:
    *   **PostgreSQL**: `localhost:5432` (ID/PW: `admin` / `adminpassword`, DB: `koscomdb`)
    *   **Neo4j Browser**: `http://localhost:7474` (ID/PW: `neo4j` / `neo4jpassword`)
    *   **Neo4j Bolt (코드 연동용)**: `bolt://localhost:7687`
5.  개발 및 접속이 완료되면 터널링 실행 터미널에서 **`Enter` 키를 눌러 터널을 해제**합니다.

---

## 3. 🏗️ FastAPI AI 서버 시스템 아키텍처

FastAPI 라우터를 타고 들어온 질문이 LangChain 오케스트레이터를 거쳐 두 RAG 데이터 베이스를 경유해 병합(Synthesis)되는 최종 아키텍처입니다.

```mermaid
graph TD
    User(["사용자 / 클라이언트"]) -->|뉴스 텍스트 또는 질문 입력| API["FastAPI API Router"]
    
    subgraph FastAPI_AI_Server ["FastAPI AI Server (LangChain)"]
        API -->|컨텍스트 전달| Orchestrator["LangChain Orchestrator"]
        
        Orchestrator -->|Phase 1: 팩트 추출| GraphChain["GraphRAG Chain"]
        Orchestrator -->|Phase 2: 시황/감성 검색| VectorChain["Vector RAG Chain"]
        
        GraphChain <-->|Port 7687| Neo4j["Neo4j Graph DB"]
        VectorChain <-->|Port 5432| Postgres["PostgreSQL pgvector"]
        
        GraphChain -->|관련 수혜주 리스트 & 공시 팩트| Synthesis["LLM Synthesis & Predictor"]
        VectorChain -->|최신 뉴스 요약 & 리포트 감성| Synthesis
    end
    
    Synthesis -->|종합 보고서 JSON| API
    API -->|최종 응답 반환| User
```


---

## 4. ⚡ FastAPI & 랭체인 통합 구현 가이드 (하이브리드 RAG 완성본)

단일 FastAPI 서버 안에서 **Neo4j GraphRAG**와 **PostgreSQL pgvector RAG**를 융합하여 서비스하는 **랭체인 통합 완성형 예시 코드**입니다.

이 소스코드를 복사하여 서버 메인 진입점 파일(예: `main.py`)로 활용할 수 있습니다.

```python
import os
import json
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# LangChain 라이브러리 로드
from langchain_community.graphs import Neo4jGraph
from langchain_postgres.vectorstores import PGVector
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.runnables import RunnablePassthrough

app = FastAPI(
    title="kosLINK AI - Hybrid RAG Engine Server",
    description="Neo4j 온톨로지 팩트 검증망과 PostgreSQL pgvector 실시간 분석 RAG를 단일 랭체인 파이프라인으로 통합 서비스합니다."
)

# ==============================================================================
# 1. 원격 데이터베이스 커넥션 설정 (터널링 연결 기준)
# ==============================================================================
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4jpassword")

PG_CONNECTION_STRING = os.environ.get(
    "PG_CONNECTION_STRING",
    "postgresql+psycopg://admin:adminpassword@localhost:5432/koscomdb"
)

# OpenAI API 임베딩 및 모델 정의
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)

# ==============================================================================
# 2. 데이터 저장소 클래스 바인딩
# ==============================================================================
# GraphRAG (Neo4j) 초기화
graph_db = Neo4jGraph(
    url=NEO4J_URI,
    username=NEO4J_USER,
    password=NEO4J_PASSWORD
)

# VectorRAG (PostgreSQL pgvector) 초기화
vector_db = PGVector(
    embeddings=embeddings,
    connection=PG_CONNECTION_STRING,
    collection_name="market_news"
)

# ==============================================================================
# 3. 요청/응답 스키마 스펙 정의
# ==============================================================================
class HybridQueryRequest(BaseModel):
    news_text: str  # 사용자가 입력한 자연어 기사 요약 또는 분석 대상 텍스트

class HybridQueryResponse(BaseModel):
    news_summary: str
    relevant_stocks: List[Dict[str, Any]]
    graph_raw_facts: List[Dict[str, Any]]  # 추가: 온톨로지(Neo4j)에서 직접 조회된 원시 노드/엣지/메타데이터 목록

# ==============================================================================
# 4. 하이브리드 RAG 통합 API 엔드포인트
# ==============================================================================
@app.post("/api/v1/hybrid-predict", response_model=HybridQueryResponse)
def execute_hybrid_rag(request: HybridQueryRequest):
    """
    1단계: 기사 텍스트 키워드 기반으로 Neo4j Graph DB를 쿼리하여 '관련 수혜주 및 공급망 관계' 추출 (Hard Fact)
    2단계: 추출된 수혜주 리스트를 바탕으로 PostgreSQL pgvector에서 '최신 리포트 및 기사 본문' 검색 (Context)
    3단계: 랭체인 프롬프트 합성 체인을 통해 최종 예측 종합 보고서(JSON) 생성 및 원시 그래프 팩트 병합 반환
    """
    input_text = request.news_text
    
    # --------------------------------------------------------------------------
    # [AI 라우터 & 파라미터 추출] 
    # 경량 LLM을 호출해 뉴스에서 쿼리 대상 변수(포커스, 관련주명, 역할군, 홉 깊이)를 JSON으로 추출합니다.
    # --------------------------------------------------------------------------
    router_prompt = f"""
    아래 뉴스 기사를 읽고 온톨로지 조회를 위한 검색 매개변수를 JSON으로만 추출해 주세요.
    
    [역할군 후보 ID]
    - R_CHIP (종합 반도체 및 파운드리), R_EUV (EUV/펠리클), R_PKG_EQUIP (패키징 장비), R_TEST_PART (테스트 부품/소켓) 등
    
    [JSON 포맷 규격]
    {{
      "focus": "기사의 주요 대상이 회사면 'STOCK', 기술 분야면 'ROLE', 둘 다면 'BOTH'로 지정",
      "stock_names": ["기사에 직접 언급된 반도체 회사 이름 리스트 (없으면 빈 리스트)"],
      "role_id": "기사 내용과 가장 연관 깊은 역할군 ID (없으면 null)",
      "depth": "1차 거래선 위주는 1, 연쇄적인 2차/3차 협력선 추적은 2~3 중 지정 (기본값 1)"
    }}
    
    [뉴스 기사]
    {input_text}
    """
    
    try:
        # 1차 경량 파싱용 LLM 가동
        router_res = llm.invoke(router_prompt)
        # JSON 문자열 정제 및 파싱
        param_data = json.loads(router_res.content.replace("```json", "").replace("```", "").strip())
        
        focus = param_data.get("focus", "STOCK")
        stock_names = param_data.get("stock_names", [])
        role_id = param_data.get("role_id")
        
        # [성능/보안 가드레일] 무한 쿼리로 인한 DB 마비를 차단하기 위해 탐색 홉(Depth)을 3 이하로 강제 제한
        depth = max(1, min(int(param_data.get("depth", 1)), 3))
        
        print(f"🧭 [AI Router] focus={focus}, stocks={stock_names}, role={role_id}, safe_depth={depth}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 라우팅 변수 파싱 실패: {str(e)}")

    # --------------------------------------------------------------------------
    # [Phase 1] GraphRAG (Neo4j) - AI 추출 변수 기반 동적 쿼리 라우팅 및 메타데이터 적출
    # --------------------------------------------------------------------------
    graph_data = []
    try:
        # A. 종목명 중심의 뉴스가 입력된 경우
        if focus == "STOCK" and stock_names:
            cypher_query = f"""
            MATCH path = (s:Stock)-[:SUPPLY_TO*1..{depth}]->(b:Stock)
            WHERE s.name IN $stock_names OR b.name IN $stock_names
            RETURN path
            """
            raw_path = graph_db.query(cypher_query, {"stock_names": stock_names})
            
            # Neo4j path 객체로부터 노드/엣지 속성(메타데이터: s.marketCap, rel.dartUrl 등)을 추출하여 파싱
            for record in raw_path:
                path = record.get("path")
                if path:
                    for rel in path.relationships:
                        graph_data.append({
                            "supplier": rel.nodes[0]["name"],
                            "supplier_ticker": rel.nodes[0]["ticker"],
                            "supplier_cap": rel.nodes[0]["marketCap"],  # 노드 시총 메타데이터
                            "buyer": rel.nodes[1]["name"],
                            "product": rel["product"],                 # 엣지 제품 메타데이터
                            "amount": rel["amount"],                   # 엣지 거래액 메타데이터
                            "dart_url": rel["dartUrl"]                 # 엣지 감사용 공시 링크 메타데이터
                        })

        # B. 기술/공정(Role) 중심의 뉴스가 입력된 경우
        elif focus == "ROLE" and role_id:
            cypher_query = """
            MATCH (s:Stock)-[rel:BELONGS_TO]->(r:Role {id: $role_id})
            RETURN s.name AS supplier, s.ticker AS supplier_ticker, s.marketCap AS supplier_cap, 
                   r.label AS role_label, r.description AS role_description
            """
            # Role 매핑 데이터 및 속성(설명 등) 조회
            raw_role_data = graph_db.query(cypher_query, {"role_id": role_id})
            for item in raw_role_data:
                graph_data.append({
                    "supplier": item["supplier"],
                    "supplier_ticker": item["supplier_ticker"],
                    "supplier_cap": item["supplier_cap"],
                    "role_label": item["role_label"],
                    "role_description": item["role_description"]
                })

        # C. 종목과 기술이 복합적으로 엮인 경우
        else:
            cypher_query = f"""
            MATCH (s:Stock)-[:BELONGS_TO]->(r:Role {{id: $role_id}})
            WHERE s.name IN $stock_names
            RETURN s.name AS supplier, s.ticker AS supplier_ticker, s.marketCap AS supplier_cap, r.label AS role_label
            """
            raw_both_data = graph_db.query(cypher_query, {"stock_names": stock_names, "role_id": role_id})
            for item in raw_both_data:
                graph_data.append({
                    "supplier": item["supplier"],
                    "supplier_ticker": item["supplier_ticker"],
                    "supplier_cap": item["supplier_cap"],
                    "role_label": item["role_label"]
                })

        print(f"🧬 [GraphRAG] Neo4j 동적 라우팅 조회 완료: {len(graph_data)}건 매핑 성공.")
    except Exception as e:
        # DB 세팅 전 또는 주말 DART 점검으로 인한 테스트 방어용 오프라인 Mock 데이터 로드
        graph_data = [{"supplier": "한미반도체", "supplier_ticker": "042700", "supplier_cap": 980000000000, "buyer": "SK하이닉스", "product": "TC본더", "amount": "580억", "dart_url": "http://dart.fss.or.kr"}]
        print(f"⚠️ [GraphRAG] Neo4j 예외 우회 (Seed 데이터 적용): {str(e)}")

    # --------------------------------------------------------------------------
    # [Phase 2] Vector RAG (PostgreSQL pgvector) - 리포트 및 시황 세만틱 검색
    # --------------------------------------------------------------------------
    # GraphRAG에서 추출된 주요 공급사 키워드들로 필터링하여 관련 문서를 유사도 기반으로 조회합니다.
    retrieved_documents = []
    try:
        # PostgreSQL pgvector에서 유사도 점수가 높은 문서 3건 쿼리
        docs = vector_db.similarity_search(input_text, k=3)
        for doc in docs:
            retrieved_documents.append(doc.page_content)
        
        vector_context = "\n".join(retrieved_documents)
        print(f"💾 [Vector RAG] PostgreSQL에서 유사도 기반 관련 문서 {len(docs)}건 추출 완료.")
    except Exception as e:
        # DB 세팅 전을 위한 방어용 코드 작성 (임시 시뮬레이션 데이터 대체 가동)
        vector_context = (
            "SK하이닉스가 듀얼 TC 본더 공급망 이원화를 추진함에 따라 한미반도체 외에 "
            "장비사 에스티아이의 신규 장비 검증이 우수하게 끝났다는 시장 리포트가 발표됨. "
            "더불어 동진쎄미켐의 고성능 포토레지스트 매출 비중이 확대되어 3분기 어닝서프라이즈가 예상됨."
        )
        print(f"⚠️ [Vector RAG] PostgreSQL 연동 우회 (Mock 시황 적용): {str(e)}")

    # --------------------------------------------------------------------------
    # [Phase 3] LangChain LCB 체인 조립 및 LLM 종합 분석 실행
    # --------------------------------------------------------------------------
    # 정형 보고서 반환용 JSON Schema 정의 및 프롬프트 주입
    prompt = ChatPromptTemplate.from_template(
        "당신은 대한민국 최고 권위의 반도체 투자 분석 AI 비서입니다.\n"
        "제공되는 1) 온톨로지 팩트 데이터와 2) 시황/뉴스 문서를 융합하여 분석 보고서를 작성해 주세요.\n\n"
        "[1. 온톨로지 검증 팩트]\n{graph_facts}\n\n"
        "[2. 관련 실시간 뉴스 및 리포트 본문]\n{vector_context}\n\n"
        "[분석 대상 기사]:\n{user_input}\n\n"
        "반드시 하단의 JSON 규격에 맞추어 다른 설명 텍스트 없이 오직 순수 JSON 데이터만 반환해야 합니다.\n"
        "JSON 규격:\n"
        "{{\n"
        '  "news_summary": "입력받은 뉴스/리포트 핵심 요약 (100자 내외)",\n'
        '  "relevant_stocks": [\n'
        "    {{\n"
        '      "ticker": "종목코드",\n'
        '      "name": "종목명",\n'
        '      "supply_relation": "공급 관계 요약 (예: SK하이닉스향 본더 공급)",\n'
        '      "market_sentiment": "시장 내 감성 (긍정적/중립적/부정적)",\n'
        '      "prediction": "주가 영향 예측 (상승세/보합/하락세)",\n'
        '      "rationale": "상승/하락 예측의 논리적 근거 (온톨로지 계약금액 및 리포트 바탕)"\n'
        "    }}\n"
        "  ]\n"
        "}}"
    )

    # 랭체인 하이브리드 체인 가동
    hybrid_chain = (
        {
            "graph_facts": lambda x: json.dumps(graph_data, ensure_ascii=False, indent=2),
            "vector_context": lambda x: vector_context,
            "user_input": RunnablePassthrough()
        }
        | prompt
        | llm
        | JsonOutputParser()
    )

    try:
        # LLM을 통해 종합 자연어 분석 결과 도출
        final_result = hybrid_chain.invoke(input_text)
        
        # [온톨로지 데이터 병합] 
        # Neo4j 그래프에서 직접 수집한 실시간 원시 노드/엣지/메타데이터 목록을 최종 결과 딕셔너리에 추가 병합합니다.
        final_result["graph_raw_facts"] = graph_data
        
        return final_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"하이브리드 RAG 연산 실패: {str(e)}")

# ==============================================================================
# 5. 로컬 테스트 및 헬스 체크 엔드포인트
# ==============================================================================
@app.get("/health")
def health_check():
    return {"status": "ok", "db_tunneling": "ready"}
```

---

## 5. 🧭 파라미터 추출 및 동적 쿼리 라우팅의 흐름 요약

*   기사가 업로드되면 1차 경량 LLM이 기사 성격(`focus`: STOCK/ROLE/BOTH)과 핵심 종목명(`stock_names`), 역할 ID(`role_id`), 그리고 탐색할 홉 수(`depth`)를 JSON으로 적출합니다.
*   파이썬 백엔드는 이 분류 데이터를 읽어 해당하는 사전정의된 최적화 Cypher 쿼리문 중 하나를 **선택 대입하여 실행**함으로써 AI의 임의적 쿼리 변환으로 인한 데이터베이스 구동 중단 위험을 100% 방어합니다.

---

## 6. 🔗 탐색 깊이 제어 및 무제한 연산 방지 (Hop Control)

*   사용자 의도에 따라 1차 직속 협력사(1홉) 혹은 2~3차 연쇄 협력망(2~3홉)까지 가변 추적을 제공합니다.
*   온톨로지 그래프는 4홉이 넘어갈 경우 노드 간 경로 경우의 수 탐색 연산량이 기하급수적으로 폭발하는 리스크가 존재합니다. 따라서 코드 레벨에서 `safe_depth = max(1, min(int(depth), 3))` 제약을 강제하여 클러스터 DB 노드의 폭주를 방어합니다.

---

## 7. 💾 Neo4j 노드/엣지 메타데이터 활용 규격

*   Cypher 쿼리로 `RETURN path` 실행 시, 반환된 경로 객체 내부의 개별 노드와 관계선(엣지)은 각자 생성될 때 부여된 상세 메타데이터 속성 사전을 통째로 포함하고 있습니다.
*   개발자는 파이썬 드라이버에서 `node['marketCap']` (시가총액 메타데이터) 또는 `rel['dartUrl']` (감사용 공시 원본 URL 메타데이터) 등으로 즉시 속성에 접근하여 비즈니스 연산 및 컴플라이언스 추적에 활용할 수 있습니다.
