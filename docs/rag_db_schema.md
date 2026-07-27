# kosLINK AI: RAG 파트 DB 스키마 설계

`rag_architecture.md` 9장의 상세 버전입니다. 전체 흐름/오케스트레이션은 [rag_architecture.md](./rag_architecture.md)를 참고하고, 이 문서는 **DB 별 테이블 컬럼 설계**만 다룹니다.

DB는 크게 두 그룹입니다.

1. **RDBMS 테이블** (PostgreSQL, `koscomdb` 내)
2. **벡터 DB** (PostgreSQL + pgvector, `langchain_postgres.PGVector`)

RDBMS 테이블은 모두 **같은 PostgreSQL 인스턴스**(`koscomdb`)를 백엔드와 AI 서버가 함께 사용합니다 — 별도 DB로 분리하지 않습니다. `news`와 `news_corpus`는 데이터 자체가 백엔드 쪽에서 구성되어 제공됩니다. 컬럼 타입/제약은 초안이며, 실제 구현 중 조정될 수 있습니다.

---

## 1. RDBMS 테이블

### 1-1. `companies` — 대상 기업 목록

| 컬럼       | 타입          | 제약        | 설명                                             |
| ---------- | ------------- | ----------- | ------------------------------------------------ |
| ticker     | varchar(20)   | PK          | 종목코드, 다른 테이블의 조인 키                   |
| corp_code  | varchar(8)    | UNIQUE      | DART Open API 조회용 고유번호(ticker와 다름, 필수) — 아래 참고 |
| name       | varchar(100)  | NOT NULL    | 기업명                                            |
| role_code  | varchar(20)   | NOT NULL    | 공급망 내 역할 분류 코드 (예: `R_CHIP`, `R_IP`) — 온톨로지 카테고리와 같은 시드 소스 공유 |
| role_name  | varchar(100)  |             | role_code의 한글 라벨 (예: "칩 제조사", "반도체 IP 설계") |
| size_tier  | varchar(10)   |             | `Large` \| `Mid` \| `Small` — 시가총액 규모 등급  |
| created_at | timestamp     | default now() | 시드 등록 시각                                 |

> 시드 예시: `[R_CHIP] 칩 제조사 삼성전자 005930 Large`, `[R_IP] 반도체 IP 설계 오픈엣지테크놀로지 394280 Small`

기업 1개 = role_code 1개(1:1)로 확정 — 위처럼 `companies`에 컬럼으로 두면 됩니다(별도 매핑 테이블 불필요).

**`corp_code`에 `NOT NULL`을 걸지 않은 이유 (2026-07-21)**: 실제 대상 기업 시드 데이터(`rag/sql/002_seed_companies.sql`)엔 종목코드만 있고 DART `corp_code`는 없습니다 — `shared/dart_client.resolve_corp_code(ticker)`로 별도 조회해서 채워야 하는 값이라, 시드 시점엔 비어있을 수밖에 없습니다. `UNIQUE`는 유지하고(Postgres는 NULL 여러 개를 UNIQUE 위반으로 안 봄), 공시(`disclosures`) 수집 전에는 반드시 채워야 한다는 제약은 DB가 아니라 애플리케이션(ingestion 전 체크)에서 강제합니다.

### 1-2. `disclosures` — DART 공시 원문

| 컬럼                | 타입         | 제약  | 설명                                     |
| ------------------- | ------------ | ----- | ---------------------------------------- |
| rcept_no            | varchar(14)  | PK    | DART 접수번호 — 자연 키이자 멱등 식별자    |
| corp_code           | varchar(8)   | FK → companies.corp_code | 공시 주체 기업            |
| report_nm           | varchar(200) |       | 보고서명                                  |
| rcept_dt            | date         |       | 접수일자                                  |
| raw_text            | text         |       | 원문 텍스트 — 아래 참고                    |
| source_url          | text         |       | DART 원문 링크                            |
| ingested_at         | timestamp    | default now() | 수집(원문 저장) 시각                |
| rag_embedded_at     | timestamp    | nullable | RAG 임베딩 완료 시각                   |
| ontology_learned_at | timestamp    | nullable | 온톨로지 학습 완료 시각                |

**사전 적재와 향후 주기적 폴링을 같은 테이블로 관리 (2026-07-21 확정)**: 공시는 뉴스와 달리 개별 건마다 "응답을 생성"하는 라이프사이클이 없고(온톨로지+RAG 학습/임베딩 코퍼스에 편입되는 용도로만 쓰임), 사전 적재든 이후 주기적 폴링이든 필요한 컬럼이 동일합니다. `rcept_no`가 DART 자연키라 재적재/재폴링해도 자동으로 멱등성이 보장되므로, `news`/`news_corpus`처럼 테이블을 분리하지 않고 이 테이블에 계속 적재합니다.

**`raw_text`에 실제로 들어가는 값 (2026-07-21 확정)**: DART 원본은 XML(ZIP)로 내려오지만, 이 XML을 직접 파싱하지 않습니다. `shared/dart_client`의 `DartOpenApiClient.get_business_report_text(rcept_no, max_chars=...)`가 이미 ZIP을 받아 BeautifulSoup으로 태그를 제거하고 정리한 **plain text**를 반환합니다(`shared/dart_client/client.py`) — `raw_text`엔 이 반환값을 그대로 저장합니다. 컬럼 타입은 그냥 Postgres `text`면 충분하고, 별도의 파일/XML 저장 방식은 필요 없습니다.

- 원문을 DB에 저장하는 이유: 청크 분할/임베딩이 이 텍스트를 반복해서 필요로 하는데, 저장 안 해두면 재청킹·재임베딩할 때마다 DART API를 다시 호출해야 합니다 (레이트리밋, 데모 당일 DART 장애 위험). 한 번 받아서 캐시해두는 게 안전합니다.
- `get_business_report_text`는 기본 `max_chars=20000`이고 "사업의 개요" 마커가 있으면 그 지점부터 자릅니다(온톨로지팀이 관계 추출용으로 그렇게 튜닝함). RAG는 더 넓은 범위가 필요하면 호출 시 `max_chars`를 크게 넘겨서 쓰면 됩니다 — 마커가 없는 공시 유형이면 전체 텍스트가 그대로 반환되므로 사업보고서 외 다른 공시 타입에도 재사용 가능합니다.

### 1-3. `news_corpus` — 사전 학습용 과거 뉴스 원문

데이터는 **백엔드 쪽에서 구성해서 제공**합니다. `news`와 동일하게, RAG·온톨로지 각각의 학습 완료 시각을 컬럼으로 구분합니다.

| 컬럼                | 타입        | 제약        | 설명                              |
| ------------------- | ----------- | ----------- | ---------------------------------- |
| news_id             | bigint      | PK          | 백엔드가 부여하는 안정적 ID (RAG가 생성 X) |
| title               | text        |             | 제목                                |
| body                | text        |             | 본문                                |
| press               | varchar(100)|             | 언론사                              |
| url                 | text        |             | 원문 링크                           |
| published_at        | timestamp   |             | 실제 발행 시각                      |
| created_at          | timestamp   | default now() | 백엔드가 이 행을 제공한 시각      |
| rag_embedded_at     | timestamp   | nullable    | RAG 임베딩 완료 시각                |
| ontology_learned_at | timestamp   | nullable    | 온톨로지 학습 완료 시각             |

`news`와 `news_corpus` 둘 다 백엔드가 저장/제공하는 데이터라, PK도 백엔드가 부여하는 안정적인 ID를 그대로 씁니다 (`bigserial`로 RAG가 별도 생성하지 않음) — `disclosures`가 DART의 자연키(`rcept_no`)를 PK로 쓰는 것과 같은 이유로, 재적재해도 중복이 안 생깁니다.

### 1-4. `news` — 실시간 폴링 뉴스

데이터는 **백엔드 쪽에서 구성해서 제공**합니다 (1분 폴링 → 저장). 실제 컬럼명은 백엔드팀과 확정이 필요하며, 아래는 RAG 입장에서 필요한 컬럼 제안입니다.

| 컬럼                | 타입        | 설명                                                        |
| ------------------- | ----------- | ------------------------------------------------------------ |
| news_id             | bigint      | PK                                                            |
| title / body / url / press / published_at | ... | 뉴스 원문 메타데이터                              |
| status              | varchar(20) | PENDING \| ANALYZING \| DONE \| FAILED — 백엔드가 PENDING으로 적재, 이후 AI 서버가 갱신 (실운영 데이터 기준 대문자, DB에 CHECK 제약 없음) |
| analyzed_at         | timestamp   | nullable, AI 서버가 `ai_responses` 저장 후 기록                |
| rag_embedded_at     | timestamp   | nullable, RAG 사후 임베딩 완료 후 기록                        |
| ontology_learned_at | timestamp   | nullable, 온톨로지 사후 학습 완료 후 기록                      |

- "응답 구성 여부" 하나의 boolean 대신 단계별 컬럼으로 나눈 이유: 응답 생성(analyzed_at)과 사후 임베딩(rag_embedded_at) / 온톨로지 학습(ontology_learned_at)이 서로 다른 시점에 끝나는 별개 작업이라, 나중에 "응답은 있는데 임베딩만 실패" 같은 상황을 구분하기 위함입니다.
- 뉴스 리스트 조회 시 프론트 노출 여부를 `status='DONE'`만으로 필터링하면 안 됩니다 — `origin_stocks`가 없는(유니버스 밖) 뉴스도 `DONE`으로 갱신되지만 `ai_responses`엔 행이 없습니다(1-5절 참고). 응답이 있는 뉴스만 보여주려면 `ai_responses`에 해당 `news_id` 행이 있는지로 판단해야 합니다.
- AI 서버가 이 테이블의 상태 컬럼을 갱신할 수 있는 범위(쓰기 권한)는 백엔드 팀과 별도 확인이 필요합니다.

### 1-5. `ai_responses` — AI 서버가 직접 저장하는 뉴스별 분석 응답

**2026-07-27 응답 포맷 개편**: `key_companies`/`derived_companies`(evidence_sources 포함) 구조를 `origin_stocks`/`related_stocks`/`final_summary`/`graph`로 재구성했습니다. `evidence_sources`는 응답에서 제거됨 — LLM이 `related_stocks.propagation` 문구를 쓸 때 내부 근거로만 쓰고 더 이상 응답에 노출하지 않습니다 (`rag/sql/005_update_ai_responses_new_format.sql`).

| 컬럼               | 타입         | 제약        | 설명                                                        |
| ------------------ | ------------ | ----------- | ------------------------------------------------------------ |
| id                 | bigserial    | PK          |                                                                |
| news_id            | bigint       | NOT NULL, UNIQUE | `news` 테이블의 news_id (앱 레벨 FK — 실제 DB 제약 여부는 미정) |
| news_summary       | jsonb        |             | 뉴스 3줄 요약. `["문장1", "문장2", "문장3"]`                    |
| source             | jsonb        |             | 뉴스 메타 정보(응답 조립 시 `news` 테이블에서 옮겨 담음). `{press, published_at, url}` |
| origin_stocks      | jsonb        |             | 뉴스가 실제로 다루는 메인 기업 — LLM이 companies 유니버스(51개) 안에서 최대 1개만 추출(배열이지만 0~1개). `[{ticker, name, status: "up"\|"down", reason}]` |
| related_stocks     | jsonb        |             | 온톨로지로 찾은 연관 기업. `ticker`/`name`/`relation_label`/`relation_path`는 온톨로지 하드 팩트, `status`/`propagation`만 LLM이 채움. `[{ticker, name, status: "up"\|"down", relation_label, relation_path, propagation}]` |
| final_summary      | text         |             | 응답 전체를 종합한 3문장 내외 요약                              |
| graph              | jsonb        |             | 프론트 그래프 시각화용 노드/엣지 — `originId`/`nodes`/`edges`는 온톨로지 `OntologyExploreResult.graph`를 그대로 저장(RAG는 패싱만, origin_stocks가 여럿이면 결과를 합침), `newsId`만 RAG가 채움. `{newsId, originId, nodes: [{id, name, ticker, marketType, capSize}], edges: [{id, source, target, relation}]}` |
| status             | varchar(20)  | default 'done' | done \| failed                                            |
| error_message      | text         | nullable    | LLM/조회 실패 시 원인 기록                                     |
| created_at         | timestamp    | default now() |                                                              |

- `origin_stocks`와 `related_stocks`를 별도 컬럼으로 나눈 이유: "뉴스에 나온 주요 기업"과 "그로부터 파생된 연관 기업"은 성격이 달라서(전자는 텍스트 추출, 후자는 온톨로지 그래프 순회가 핵심) 나중에 각각 다르게 조회/가공하기 쉽도록 분리. 둘 다 정규화 대신 JSONB로 저장하는 건 MVP 범위에선 그대로 유지합니다.
- `source`를 `news` 테이블과 별도로 다시 저장하는 이유: 응답 조립("검색/추출 결과 → 바로 응답에 사용")이 매 조회마다 `news`를 다시 join하지 않도록, 2-1절의 `cmetadata` denormalize 방침과 같은 이유로 적재 시점에 한 번 옮겨 담습니다.
- `graph`를 RAG가 직접 조립하지 않는 이유: 노드에 필요한 `marketType`/`capSize` 같은 값이 지금 RAG 쪽 테이블에는 없고, 온톨로지 파트(`ontology_client.find_related_companies`)가 그래프 순회(2-hop) 결과를 이미 노드/엣지 형태로 구성해 넘겨주기 때문입니다. RAG는 이 값을 그대로 저장/패싱만 합니다.
- `news_id`에 UNIQUE를 걸어 "한 뉴스 = 응답 1건"을 보장. 재분석이 필요하면 upsert로 덮어씁니다(버전 이력이 필요해지면 이후 별도 검토).
- **`origin_stocks`가 비어 있는 뉴스(companies 유니버스 51개와 무관한 뉴스)는 이 테이블에 행 자체가 생기지 않습니다 (2026-07-27 확정)**: `news.status`는 정상적으로 `'DONE'`까지 갱신되지만(재처리 대상에서는 빠짐), 보여줄 분석 결과가 없다고 판단해 `ai_responses` insert를 생략합니다. 그래서 **"응답 구성 여부"는 반드시 이 테이블에 `news_id` 행이 있는지로 판단해야 하고, `news.status='DONE'`만으로는 응답이 있다고 보장할 수 없습니다** (1-4절의 "후자가 더 간단" 설명은 더 이상 유효하지 않음).

### 1-6. `rag_ingestion_log` — 임베딩 처리 로그 (멱등성 보장)

| 컬럼            | 타입        | 제약   | 설명                                                                 |
| --------------- | ----------- | ------ | ---------------------------------------------------------------------- |
| id              | bigserial   | PK     |                                                                          |
| source_type     | varchar(20) | NOT NULL | disclosure \| report \| news_backfill \| news_realtime               |
| source_doc_id   | varchar(50) | NOT NULL | 공시는 `rcept_no`, 뉴스는 `news_id`                                    |
| ticker          | varchar(20) |        |                                                                          |
| chunk_count     | int         |        | 이 문서에서 생성된 청크 수                                              |
| ingested_at     | timestamp   | default now() |                                                                    |
| UNIQUE          |             |        | `(source_type, source_doc_id)`                                          |

사전 적재(`preload_corpus.py`)와 실시간 뉴스 사후 임베딩 모두 이 테이블 하나로 관리합니다 — 재실행/재시도 시 이미 적재된 `(source_type, source_doc_id)`를 확인해 기존 청크를 지우고 다시 넣어 중복 벡터를 방지합니다.

---

## 2. 벡터 DB (PostgreSQL + pgvector, `langchain_postgres.PGVector`)

직접 테이블을 설계하지 않고 `PGVector(collection_name=..., embeddings=...)`를 사용합니다. 아래는 실제 생성되는 테이블의 논리적 구조입니다.

### 2-0. 청크가 저장되는 방식 (핵심 개념 — prefix 아님)

핵심은 **텍스트(임베딩 대상)와 메타데이터(부가 정보)가 애초에 서로 다른 필드**라는 겁니다. 텍스트 앞에 URL/날짜를 prefix로 붙이는 방식이 아니라, LangChain의 `Document` 객체가 둘을 처음부터 분리해서 다룹니다.

```python
from langchain_core.documents import Document

chunks = splitter.split_text(disclosure.raw_text)
docs = [
    Document(
        page_content=chunk,          # ← 이 텍스트만 임베딩 모델에 들어감
        metadata={                   # ← 별도 필드로 같이 저장됨 (임베딩 계산엔 관여 안 함)
            "ticker": ticker,
            "source_type": "disclosure",
            "source_doc_id": disclosure.rcept_no,   # 어떤 공시/뉴스에서 왔는지
            "chunk_index": i,
            "title": disclosure.report_nm,          # 응답 조립 시 바로 쓸 표시용 정보
            "url": disclosure.source_url,
            "published_date": str(disclosure.rcept_dt),
        },
    )
    for i, chunk in enumerate(chunks)
]
vector_store.add_documents(docs)
```

`add_documents()`를 호출하면 PGVector가 `page_content`는 `document` 컬럼 + 임베딩해서 `embedding` 컬럼에, `metadata` dict는 통째로 `cmetadata`(jsonb) 컬럼에 저장합니다. 즉 "이 청크가 어떤 뉴스/공시인지"는 텍스트 안에 섞어 넣는 게 아니라 **같은 row의 다른 컬럼**에 구조화된 값으로 들어갑니다.

검색해서 근거(evidence_sources)를 만들 때는 검색 결과에서 바로 꺼내씁니다 (추가 조회 없음):

```python
results = vector_store.similarity_search(query, k=5, filter={"ticker": "005930"})
evidence_sources = [
    {
        "source_type": r.metadata["source_type"],
        "title": r.metadata["title"],
        "url": r.metadata["url"],
        "published_date": r.metadata["published_date"],
    }
    for r in results
]
```

`title`/`url`/`published_date`를 원본 테이블에서 매번 join해서 가져오는 대신, **적재(ingestion) 시점에 한 번만** `disclosures`/`news_corpus`/`news`의 컬럼(각각 `report_nm`/`title`, `source_url`/`url`, `rcept_dt`/`published_at`처럼 이름이 다름)을 공통 스키마로 매핑해서 `cmetadata`에 같이 넣어둡니다. 응답 조립이 "검색 → 바로 필드 사용"이라면, 이 매핑을 매 응답마다 반복하는 것보다 적재 시 한 번 해두는 쪽이 낫습니다 (2-1절 참고 — 조인 방식 대신 이 방식을 기본으로 채택).

**"prefix로 넣어야 하나?"에 대한 답**: URL/날짜처럼 의미 없는 문자열을 청크 텍스트에 섞으면 임베딩 품질만 떨어집니다(유사도 계산에 노이즈로 작용) — 이런 값은 metadata로만 다루세요. 다만 **문서 제목이나 기업명처럼 의미 있는 문맥**은 검색 품질 향상을 위해 실제로 청크 앞에 붙이는 기법이 존재합니다 (예: `"[삼성전자 2026년 1분기 분기보고서]\nHBM 공급 계약 확대에 따라..."`) — 긴 문서를 잘게 쪼개면 개별 청크만 봤을 때 "무슨 회사/문서 얘기인지" 문맥이 사라지는 경우가 있어서, 임베딩 대상 텍스트 자체에 최소한의 문맥을 얹어주는 방식입니다. 이건 선택적 품질 개선 기법이고, metadata 저장 방식과는 별개입니다 — MVP 범위에서는 굳이 넣지 않아도 되고, 검색 품질을 보면서 필요하면 나중에 추가하면 됩니다.

### 2-1. `langchain_pg_embedding` (자동 생성)

| 컬럼        | 타입          | 설명                                                                 |
| ----------- | ------------- | ---------------------------------------------------------------------- |
| id          | uuid          | PK                                                                      |
| collection_id | uuid        | FK → langchain_pg_collection.uuid                                      |
| document    | text          | 청크 텍스트 (임베딩 계산에 실제 반영되는 값)                            |
| embedding   | vector(3072)  | 임베딩 벡터 (기본 프로바이더 OpenAI `text-embedding-3-large` 기준 3072차원 - KURE/BGE-M3로 바꾸면 1024차원이라 기존 컬렉션과 호환 안 됨, 재임베딩 필요) |
| cmetadata   | jsonb         | 메타데이터 전체 (아래 참고)                                             |

`cmetadata`는 `langchain_postgres.PGVector`가 테이블을 자동 생성할 때 기본으로 만드는 **단일 jsonb 컬럼**입니다 — `PGVector(...).add_documents()`에 넘긴 `Document.metadata` dict가 그대로 이 컬럼에 통째로 들어갑니다. 별도로 컬럼을 나눠서 만들어주지 않고, 조회 시에도 `cmetadata->>'ticker'` 식으로 jsonb 연산자를 거쳐야 접근됩니다.

**`cmetadata`에 뭘 담을지 — 채택 (2026-07-21 확정): 응답 조립에 필요한 값을 전부 denormalize해서 담기**

```json
{ "ticker": "005930", "source_type": "disclosure", "source_doc_id": "20260105000123", "chunk_index": 1, "title": "분기보고서", "url": "https://...", "published_date": "2026-01-05" }
```

- `ticker`/`source_type` — 검색 필터링용 (`WHERE` 조건)
- `source_doc_id`/`chunk_index` — 원본 추적, 재적재 멱등성 관리용
- `title`/`url`/`published_date` — 응답의 `evidence_sources`에 바로 꽂아 넣을 표시용 정보

응답 조립이 "벡터 검색 → 결과를 바로 응답에 사용" 흐름이라, `disclosures`/`news_corpus`/`news` 각각 다른 컬럼명(`report_nm` vs `title` 등)을 매번 매핑하느니 적재 시점에 한 번 정규화해서 넣어두는 쪽이 낫다고 판단했습니다 (2-0절 참고). 참고로 검토했던 대안들:

1. ~~참조 키만 남기고 나머지는 join~~ — 중복은 없지만 응답 생성 시마다 `source_type`별로 분기해서 원본 테이블을 다시 조회해야 해서 기각.
2. **jsonb 위에 generated column 추가**: `PGVector`가 테이블을 만든 뒤, `vectordb/` 부트스트랩 스크립트에서 `ALTER TABLE langchain_pg_embedding ADD COLUMN ticker text GENERATED ALWAYS AS (cmetadata->>'ticker') STORED;` 식으로 자주 필터링하는 필드만 실컬럼처럼 뽑아내고 인덱스를 거는 방법. `ticker`/`source_type`처럼 필터링에 쓰는 필드에 한해 검색 성능이 실제로 병목일 때 추가로 고려 (denormalize 방침과는 별개로 병행 가능).

- `source_type`은 `disclosure` / `report` / `news_backfill` / `news_realtime` 네 가지.
- 검색 시 `cmetadata`의 `ticker`/`source_type`으로 먼저 필터링한 뒤 벡터 거리(`<=>`)로 top-k 정렬.

### 2-2. `langchain_pg_collection` (자동 생성)

| 컬럼      | 타입  | 설명                     |
| --------- | ----- | ------------------------ |
| uuid      | uuid  | PK                        |
| name      | text  | collection 이름           |
| cmetadata | jsonb | collection 레벨 메타데이터 |

**Collection 구성 제안**: 공시/리포트/과거 뉴스/실시간 뉴스를 하나의 collection(예: `market_evidence`)에 모아 `source_type` 필터로 구분하는 방식을 추천합니다 — "판단 근거"가 공시든 과거 뉴스든 한 번의 유사도 검색에서 함께 랭킹되어야 하므로, 소스별로 collection을 쪼개면 검색 시 여러 번 질의하거나 결과를 다시 병합해야 하는 번거로움이 생깁니다.
