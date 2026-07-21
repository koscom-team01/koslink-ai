# kosLINK AI: RAG(Vector RAG) 파트 아키텍처 명세서

본 문서는 **RAG 개발팀**이 개발하는 `rag/` 서비스(FastAPI + LangChain)의 폴더 구조, 데이터베이스 연결 구조, 임베딩 프로바이더 인터페이스, 온톨로지(GraphRAG)와의 융합 방식을 정의합니다. Neo4j 온톨로지 쪽 설계는 [ontology_architecture.md](./ontology_architecture.md)를, DB 테이블 컬럼 단위 설계는 [rag_db_schema.md](./rag_db_schema.md)를 참고하세요.

---

## 0. 서비스 전체 흐름 (3-Tier 아키텍처)

서비스는 **프론트 / 백엔드 / AI 서버** 3계층으로 나뉘고, 본 레포(`koslink-ai`)가 그 중 **AI 서버**입니다. AI 서버 내부는 온톨로지와 RAG가 각각 독립적으로 FastAPI 앱까지 구축된 뒤, 최종적으로 LangChain 기반 체인으로 결합됩니다(2절 참고). 서비스가 사용자에게 제공하는 것은 두 가지입니다.

1. 반도체 기업 간 관계를 온톨로지 기반 3D 그래프로 시각화 (관련주 개념)
2. 실시간 뉴스에 대해: 주요 기업 / 파생·연관 기업(온톨로지+RAG 기반) / 판단 근거(파급경로=온톨로지, 과거 이벤트=RAG) 제공

**사전 준비 단계**: 온톨로지와 RAG는 같은 소스 데이터 — ① 대상 기업 리스트, ② 과거 뉴스 데이터, ③ DART 공시 — 를 기반으로 각자 방식(온톨로지: Neo4j 그래프, RAG: pgvector 임베딩)으로 사전 학습/임베딩을 마쳐둡니다.

**실시간 흐름**:

```
[백엔드] 1분마다 최신 뉴스 폴링
    → 뉴스 원문을 백엔드 DB에 저장
    → AI 서버 호출 (POST /api/v1/news/{news_id}/analyze)

[AI 서버 = 온톨로지 + RAG]
    → 뉴스 요약, 주요 기업, 연관/파생 기업, 판단 근거(파급경로+과거 이벤트) 구성
    → 이 응답을 AI 서버가 직접 DB에 저장 (동기 반환뿐 아니라 저장까지 AI 서버 책임)
    → 저장 완료 후, 같은 뉴스를 온톨로지·RAG가 각각 사후 학습/임베딩
      (다음 뉴스 분석 때 "과거 이벤트" 근거로 쓰이도록 코퍼스에 편입)

[프론트]
    → 사용자가 뉴스 조회 시, 백엔드가 DB에 저장된 AI 서버 응답을 그대로 조회해서 보여줌
    → AI 서버가 아직 응답을 구성하지 못한 뉴스는 뉴스 리스트 조회에서 제외
```

프론트는 AI 서버를 직접 호출하지 않습니다 — 항상 백엔드가 중개하고, AI 서버 응답은 항상 DB를 거쳐 전달됩니다.

---

## 1. 레포지토리 내 DB 관련 폴더 3종의 역할 구분

**연결 순서**: `connect_db.sh`로 터널 오픈 → (최초 1회, 또는 스키마 변경 시) `vectordb/`의 부트스트랩 스크립트 실행 → `rag/app/db/`가 매 요청마다 그 위에서 CRUD 수행.

로컬 개발 시 두 사람 모두 README 2장 안내대로:

```bash
# 1. team1-kubeconfig.yaml 을 레포 루트에 위치
# 2. 터널 실행
./connect_db.sh
```

을 켜둔 상태에서 아래 접속정보로 PostgreSQL(pgvector 포함)과 Neo4j 모두에 접근합니다.

pgvector 확장이 활성화된 동일 `koscomdb` 안에 백엔드 팀이 적재하는 뉴스 RDBMS 테이블과, RAG 팀이 적재하는 벡터 컬렉션이 공존합니다. `rag/app/db/`는 이 두 종류를 다른 방식으로 다룹니다.

---

## 2. `rag/` 폴더 구조

```
rag/
├── Dockerfile                       # (배포 단계에서 추가 예정)
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py                      # FastAPI entrypoint
│   ├── config.py                    # pydantic-settings 기반 공통 설정
│   ├── api/
│   │   ├── deps.py                  # DI: db session, embedding provider, llm 등 주입
│   │   └── routers/
│   │       ├── query.py             # POST /api/v1/rag/query
│   │       ├── ingest.py            # POST /api/v1/rag/ingest
│   │       └── summarize.py         # POST /api/v1/rag/summarize
│   ├── core/
│   │   ├── embeddings/
│   │   │   ├── base.py              # EmbeddingProvider 인터페이스 (LangChain Embeddings ABC)
│   │   │   ├── kure.py              # KURE 구현체
│   │   │   ├── bge_m3.py            # BGE-M3 구현체
│   │   │   └── factory.py           # EMBEDDING_PROVIDER 환경변수로 구현체 선택
│   │   ├── llm/
│   │   │   └── claude.py            # ChatAnthropic 래퍼
│   │   └── chains/
│   │       ├── qa_chain.py          # 벡터 컨텍스트 + 온톨로지 팩트 융합 → Claude 응답 생성
│   │       └── news_summary_chain.py
│   ├── db/
│   │   ├── session.py               # SQLAlchemy async engine/session
│   │   ├── base.py                  # Declarative Base (RAG 소유 테이블 전용)
│   │   └── models/
│   │       └── document_chunk.py    # RAG 소유 임베딩 청크 보조 테이블
│   ├── repositories/
│   │   ├── vector_repository.py     # pgvector 유사도 검색
│   │   ├── news_repository.py       # 백엔드 news 테이블 읽기 전용 조회
│   │   └── ontology_client.py       # 온톨로지(Neo4j) 조회 인터페이스
│   ├── schemas/                     # pydantic request/response 모델
│   ├── services/
│   │   ├── ingestion_service.py     # 청크 분할 + 임베딩 + 적재 오케스트레이션
│   │   └── retrieval_service.py     # 검색 + 하이브리드 컨텍스트 조립 오케스트레이션
│   └── utils/
│       └── text_splitter.py
├── scripts/
│   └── test_rag_chain.py            # 독립 체인 구동 검증 스크립트 (README 마일스톤 3)
└── tests/
```

---

## 3. 임베딩 프로바이더 인터페이스 (KURE / BGE-M3 스위칭)

LangChain의 `Embeddings` 추상클래스(`embed_documents`, `embed_query`)를 그대로 계약으로 사용합니다. `KureEmbeddings`, `BgeM3Embeddings`는 동일 인터페이스를 상속해 `model_name`만 다르게 지정하고, `factory.py`가 `EMBEDDING_PROVIDER` 환경변수(`kure` | `bge_m3`) 값으로 인스턴스를 반환합니다. `PGVector(embeddings=get_embedding_provider())` 한 줄만 바뀌면 모델 교체가 끝나는 구조입니다.

Windows/Mac 개발 환경 차이(torch 빌드, MPS/CPU 차이)로 인한 비일관성을 막기 위해, 임베딩 모델 로딩은 **Docker 컨테이너 안에서 실행**하는 것을 권장합니다. Linux 컨테이너 위에서는 두 OS 모두 CPU로 통일되어 개발자 간 환경 차이가 사라지고, 동일 이미지를 배포 환경에도 그대로 사용할 수 있습니다.

---

## 4. 하이브리드 LangChain 체인 구조

`retrieval_service.py`가 두 소스를 모아 `qa_chain.py`에 넘깁니다.

1. `ontology_client.py` → Neo4j에서 관련 종목/공급망 팩트(Hard Fact) 조회
2. `vector_repository.py` → pgvector에서 관련 뉴스/리포트 청크(Soft Info) 유사도 검색
3. 두 컨텍스트를 프롬프트에 함께 주입 → Claude(`ChatAnthropic`)가 최종 응답 합성

README 4장의 하이브리드 체인 예시(`GraphChain` + `VectorChain` → `Synthesis`)를 LCEL로 재구성한 것이며, `ontology_client.py`는 인터페이스로 분리되어 있어 추후 온톨로지팀이 자체 API를 띄우면 REST 클라이언트 구현체로 교체 가능합니다(호출부 변경 불필요).

---

## 5. 개발 환경 및 배포

- 개발 환경: 담당자 A(Windows), 담당자 B(Mac) — 각자 로컬에서 `connect_db.sh`로 DB 터널을 열고 개발

---

## 6. API 처리 흐름 (`POST /api/v1/news/{news_id}/analyze`)

라우터(`api/routers/query.py`)는 입출력만 담당하고, 실제 오케스트레이션은 `services/retrieval_service.py`, LLM 종합은 `core/chains/qa_chain.py`가 맡습니다.

```
[1] 뉴스 조회
    news_repository.get_by_id(news_id)
    → title, body, published_at, url 확보. 없으면 404.

[2] 온톨로지 조회 (Hard Fact)
    ontology_client.find_related_companies(...)
    → Neo4j에서 관련 기업/공급망 관계 리스트. 실패 시 빈 리스트로 폴백.

[3] 벡터 검색 (RAG 근거)
    vector_repository.similarity_search(
        query=news.body,
        tickers=[c.ticker for c in related],
        k=5,
    )
    → 기업별 관련 공시/리포트 청크 top-k

[4] 컨텍스트 조립
    온톨로지 팩트 + 벡터 청크를 기업별로 그룹핑한 문자열로 정리

[5] LLM 종합 (Claude)
    qa_chain.invoke({graph_facts, vector_context, news_body})
    → JSON 강제 파싱: news_summary + relevant_stocks[]

[6] 응답 조립
    LLM 결과에 [3]에서 실제 검색된 청크의 url/title/published_date를
    evidence_sources로 매칭해 붙임 (근거 없으면 "관련 근거 자료 없음" 폴백)
```

### 응답 스키마

뉴스에 직접 언급된 **주요 기업**과, 온톨로지+RAG로 찾아낸 **파생/연관 기업**을 분리합니다. 판단 근거(파급경로+과거 이벤트)는 파생 기업 쪽에 붙습니다.

```json
{
  "news_summary": "string",
  "key_companies": [
    { "ticker": "string", "name": "string" }
  ],
  "derived_companies": [
    {
      "ticker": "string",
      "name": "string",
      "derived_from": "string (key_companies 중 파생 출발점이 된 ticker)",
      "supply_relation": "string",
      "market_sentiment": "긍정적|중립적|부정적",
      "prediction": "상승세|보합|하락세",
      "rationale": "string",
      "evidence_sources": [
        { "source_type": "disclosure|report|news", "title": "...", "url": "...", "published_date": "..." }
      ]
    }
  ]
}
```

`ingest`용 HTTP 엔드포인트는 만들지 않습니다 — 공시/리포트 사전 적재는 1회성 스크립트(`scripts/preload_corpus.py`)로 처리합니다(9장 참고).

---

## 7. 임베딩 파이프라인 (전처리 → 청킹 → 임베딩)

**기본 (MVP 범위)**

- `RecursiveCharacterTextSplitter` 사용, `chunk_size≈500자`, `chunk_overlap≈80자`로 시작 (한국어 토큰 밀도 고려해 보수적으로 설정 후 검색 품질 보고 조정)
- 문서 → 섹션(제목/본문) 단위로 먼저 나누고 → 그 안에서 재귀적 분할
- 청크마다 metadata 필수 부착: `ticker, source_type, source_doc_id, chunk_index, title, url, published_date` — 응답 조립 시 매번 원본 테이블을 조인하지 않도록, 적재 시점에 원본 컬럼(예: 공시의 `report_nm`/`source_url`/`rcept_dt`)을 공통 스키마로 매핑해서 같이 저장 (8장/rag_db_schema.md 2-0·2-1절 참고)
- `source_type`은 `disclosure`(공시) / `report`(리포트) 외에 `news_backfill`(사전 학습용 과거 뉴스) / `news_realtime`(백엔드 폴링 후 사후 임베딩되는 실시간 뉴스)까지 포함합니다 — 뉴스도 공시와 동일한 임베딩 파이프라인을 재사용합니다.
- 임베딩 모델에는 `document`(청크 텍스트)만 입력되고, metadata는 검색 필터 용도로만 사용(임베딩 계산에는 관여하지 않음)
- 실시간 뉴스(`news_realtime`)는 분석 응답이 만들어진 이후 같은 파이프라인으로 사후 임베딩되어 이후 뉴스 분석의 "과거 이벤트" 근거 코퍼스에 편입됩니다. 이걸 언제·어떻게 트리거할지(동기/비동기, 실패 시 재시도 등)의 세부 오케스트레이션은 아직 미정입니다.

**고도화 백로그 (MVP 이후)**

- 하이브리드 검색 (pgvector + PostgreSQL `tsvector` 키워드 검색 병행)
- Reranking (cross-encoder, 예: bge-reranker)
- Semantic chunking (임베딩 유사도 기반 경계 탐지)
- 계층적 검색 (문서 요약 임베딩 + 세부 청크 임베딩 2단계)

전처리·청킹 세부 파라미터는 개발하면서 실제 데이터로 조정합니다.

---

## 8. 데이터 저장 스키마 (PostgreSQL + pgvector)

컬럼 단위 전체 설계(타입, PK/FK 등)는 [rag_db_schema.md](./rag_db_schema.md)에 별도로 정리했습니다. 여기서는 테이블 구성만 요약합니다.

- `companies` — 대상 기업 목록 (ticker, corp_code, name, role_code/role_name, size_tier). corp_code는 DART Open API 조회 키(8자리 고유번호, ticker와 다름)라 시드 데이터에 반드시 포함해야 합니다. role_code(예: `R_CHIP`, `R_IP`)는 온톨로지 파트의 분류 체계와 같은 시드 소스를 공유합니다.
- `disclosures` — 사전 학습용 DART 공시 원문
- `news_corpus` / `news` — 사전 학습용 과거 뉴스 원문 / 실시간 폴링 뉴스. 둘 다 데이터는 백엔드 쪽에서 구성해서 제공합니다.
- `ai_responses` — AI 서버가 직접 저장하는 뉴스별 분석 응답 (news_summary, relevant_stocks 등)
- `rag_ingestion_log` — 임베딩 처리 로그. 사전 적재(공시/과거 뉴스)와 사후 임베딩(실시간 뉴스)에 공통으로 사용해 재적재 시 중복 벡터를 막습니다.
- `langchain_pg_embedding` (`langchain_postgres.PGVector`가 자동 생성) — 실제 벡터 저장소. `document`는 오직 청크 텍스트만 반영하며, 검색 시 `ticker`/`source_type` 등 metadata로 먼저 필터링한 뒤 벡터 거리(`<=>`)로 top-k를 뽑습니다.

---

## 9. 개발 일정 및 역할 분담 (MVP: 2026-07-21(화) ~ 2026-07-24(금))

담당자 A(Windows) = 데이터·임베딩 파이프라인, 담당자 B(Mac) = API·LangChain. 매일 하루 끝에 5~10분 짧은 동기화 권장.

| 날짜    | 담당자 A (데이터·임베딩)                                                                                                                                                     | 담당자 B (API·체인)                                                                                                                                          | 체크포인트                                                                                          |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| 화 7/21 | `core/embeddings/*` 구현, `vectordb/` 부트스트랩(pgvector extension, `companies`/`disclosures`/`news_corpus` 테이블), 대상 기업 시드 데이터 입력                          | `schemas/*` Pydantic 모델, `repositories/news_repository.py`(⚠ 백엔드 news 테이블 컬럼 확인 필요), `repositories/ontology_client.py` 스텁, `repositories/response_repository.py` 스텁(`ai_responses` 저장용) | 임베딩 provider 단독 실행 확인, news_repository로 뉴스 1건 조회 성공                                  |
| 수 7/22 | `utils/text_splitter.py`, `services/ingestion_service.py`(공시 + 과거 뉴스 백필 모두 지원), `scripts/preload_corpus.py`로 실제 공시/과거 뉴스 몇 건 적재, `repositories/vector_repository.py`, `rag_ingestion_log` 연동 | `core/llm/claude.py`, `core/chains/qa_chain.py` 프롬프트+JSON 파서, `services/retrieval_service.py` 뼈대(벡터 검색은 mock)                                   | `vector_repository.similarity_search()`가 공시+과거 뉴스 모두에서 실제 pgvector 결과 반환 확인       |
| 목 7/23 | 적재 데이터 추가 보강, `ingestion_service`에 실시간 뉴스 사후 임베딩 경로 추가, 버그 픽스 지원                                                                             | `api/routers/query.py` + `api/deps.py`로 전체 조립(mock 제거), 응답을 `ai_responses`에 저장, 응답 생성 후 사후 임베딩 연결                                     | `/api/v1/news/{news_id}/analyze` end-to-end 1회 성공 — 응답 저장 + 해당 뉴스가 벡터DB에도 새로 임베딩됨 |
| 금 7/24 | 데이터 품질 보완(부족한 기업 추가 적재)                                                                                                                                     | 에러 핸들링(404, 근거 없음 폴백, 임베딩 실패해도 응답엔 영향 없도록), 응답 포맷 다듬기                                                                        | 오후: 온톨로지 파트와 통합 테스트 + 데모 리허설(사후 임베딩까지 포함한 시나리오 검증)                 |

> 사후 임베딩을 "언제·어떻게" 트리거할지(동기/비동기, 실패 재시도 등)의 세부 오케스트레이션은 아직 미정 — 위 표는 이번 주 스코프에 포함한다는 결정만 반영한 것이고, 구체적 구현 방식은 진행하며 정합니다.
