# kosLINK AI: RAG(Vector RAG) 파트 아키텍처 명세서

본 문서는 **RAG 개발팀**이 개발하는 `rag/` 서비스(FastAPI + LangChain)의 폴더 구조, 데이터베이스 연결 구조, 임베딩 프로바이더 인터페이스, 온톨로지(GraphRAG)와의 융합 방식을 정의합니다. Neo4j 온톨로지 쪽 설계는 [ontology_architecture.md](./ontology_architecture.md)를 참고하세요.

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
