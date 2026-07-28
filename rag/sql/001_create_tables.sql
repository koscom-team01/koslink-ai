-- kosLINK AI RAG 파트 RDBMS 테이블 초기 생성
-- 설계 근거: docs/rag_db_schema.md
-- 실행: ./connect_db.sh 로 터널을 연 뒤, koscomdb 대상으로
--   psql "$DATABASE_URL" -f rag/sql/001_create_tables.sql
--
-- langchain_pg_collection / langchain_pg_embedding 테이블은 여기서 만들지
-- 않습니다 — langchain_postgres.PGVector가 앱 구동 시 자동 생성합니다
-- (docs/rag_db_schema.md 2장 참고). pgvector 확장만 미리 켜둡니다.
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- 1-1. companies — 대상 기업 목록
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS companies (
    ticker      varchar(20)  PRIMARY KEY,
    -- DART Open API 조회 키(8자리). 시드 데이터엔 종목코드만 있고 corp_code는
    -- 없어서 NOT NULL을 걸지 않음 — shared/dart_client.resolve_corp_code(ticker)로
    -- 채운 뒤 UPDATE. 공시 수집 전엔 반드시 채워야 함(disclosures.corp_code가 FK).
    corp_code   varchar(8)   UNIQUE,
    name        varchar(100) NOT NULL,
    role_code   varchar(20)  NOT NULL,
    role_name   varchar(100),
    size_tier   varchar(10),
    created_at  timestamp    NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 1-2. disclosures — DART 공시 원문
-- 사전 적재와 향후 주기적 폴링 모두 이 테이블 하나로 관리(rcept_no가 자연키라
-- 멱등성 보장됨, docs/rag_db_schema.md 1-2절 참고)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS disclosures (
    rcept_no            varchar(14) PRIMARY KEY,
    corp_code           varchar(8)  NOT NULL REFERENCES companies (corp_code),
    report_nm           varchar(200),
    rcept_dt            date,
    raw_text            text,
    source_url          text,
    ingested_at         timestamp   NOT NULL DEFAULT now(),
    rag_embedded_at     timestamp,
    ontology_learned_at timestamp
);

CREATE INDEX IF NOT EXISTS idx_disclosures_corp_code ON disclosures (corp_code);

-- ---------------------------------------------------------------------------
-- 1-3. news_corpus — 사전 학습용 과거 뉴스 원문 (백엔드가 구성해서 제공)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news_corpus (
    news_id             bigint PRIMARY KEY,  -- 백엔드가 부여하는 안정적 ID
    title               text,
    body                text,
    press               varchar(100),
    url                 text,
    published_at        timestamp,
    created_at          timestamp NOT NULL DEFAULT now(),
    rag_embedded_at     timestamp,
    ontology_learned_at timestamp
);

-- ---------------------------------------------------------------------------
-- 1-4. news — 실시간 폴링 뉴스 (백엔드가 구성해서 제공)
-- ⚠ 실제 컬럼명/소유권은 백엔드팀과 확정 필요 — 아래는 RAG 입장에서의 제안
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS news (
    news_id             bigint PRIMARY KEY,
    title               text,
    body                text,
    press               varchar(100),
    url                 text,
    published_at        timestamp,
    status              varchar(20) NOT NULL DEFAULT 'pending',
    analyzed_at         timestamp,
    rag_embedded_at     timestamp,
    ontology_learned_at timestamp
);

CREATE INDEX IF NOT EXISTS idx_news_status ON news (status);

-- ---------------------------------------------------------------------------
-- 1-5. ai_responses — AI 서버가 직접 저장하는 뉴스별 분석 응답
-- news_id -> news.news_id는 앱 레벨 FK로만 관리(DB 제약 미정, rag_db_schema.md 참고)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ai_responses (
    id                bigserial   PRIMARY KEY,
    news_id           bigint      NOT NULL UNIQUE,
    news_summary      jsonb,
    source            jsonb,
    origin_stocks     jsonb,
    related_stocks    jsonb,
    final_summary     text,
    graph             jsonb,
    evidence_debug    jsonb,
    status            varchar(20) NOT NULL DEFAULT 'done',
    error_message     text,
    created_at        timestamp   NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- 1-6. rag_ingestion_log — 임베딩 처리 로그 (재적재 멱등성 보장)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rag_ingestion_log (
    id            bigserial   PRIMARY KEY,
    source_type   varchar(20) NOT NULL,  -- disclosure | report | news_backfill | news_realtime
    source_doc_id varchar(50) NOT NULL,  -- 공시: rcept_no / 뉴스: news_id
    ticker        varchar(20),
    chunk_count   int,
    ingested_at   timestamp   NOT NULL DEFAULT now(),
    UNIQUE (source_type, source_doc_id)
);
