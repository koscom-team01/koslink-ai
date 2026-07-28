-- ai_responses에 evidence_debug 컬럼 추가 - RAG 근거 적중률 분석용 내부 데이터.
-- related_stock별로 LLM이 propagation을 쓸 때 실제 RAG 근거를 참고했는지(rag)
-- 근거가 부족해 자체 추론했는지(inferred)와, 실제로 검색된 근거 청크 전체를
-- 담는다. FE 응답 계약(NewsAnalysisResponse)에는 포함되지 않는 별도 컬럼이다
-- (docs/rag_db_schema.md 1-5 참고).
--
-- 실행: ./connect_db.sh 로 터널을 연 뒤, koscomdb 대상으로
--   psql "$DATABASE_URL" -f rag/sql/006_add_ai_responses_evidence_debug.sql

BEGIN;

ALTER TABLE ai_responses
    ADD COLUMN IF NOT EXISTS evidence_debug jsonb;

COMMIT;
