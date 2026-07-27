-- ai_responses를 새 응답 포맷(origin_stocks/related_stocks/final_summary/graph)에
-- 맞춰 재구성. key_companies -> origin_stocks, derived_companies -> related_stocks로
-- 대체되고 evidence_sources는 응답에서 제거되었다 (docs/rag_db_schema.md 1-5 참고).
-- news_summary는 단일 text 요약에서 3줄 배열(jsonb)로 바뀐다.
--
-- 기존 행의 컬럼 형태 자체가 바뀌는 breaking change라 값 변환 없이 컬럼을
-- drop/add한다 - 개발 단계라 기존 응답은 재분석(POST /api/v1/news/analyze-pending)으로
-- 다시 채우면 된다.
--
-- 실행: ./connect_db.sh 로 터널을 연 뒤, koscomdb 대상으로
--   psql "$DATABASE_URL" -f rag/sql/005_update_ai_responses_new_format.sql

BEGIN;

ALTER TABLE ai_responses
    DROP COLUMN IF EXISTS key_companies,
    DROP COLUMN IF EXISTS derived_companies;

ALTER TABLE ai_responses
    ALTER COLUMN news_summary TYPE jsonb USING NULL::jsonb;

ALTER TABLE ai_responses
    ADD COLUMN IF NOT EXISTS source jsonb,
    ADD COLUMN IF NOT EXISTS origin_stocks jsonb,
    ADD COLUMN IF NOT EXISTS related_stocks jsonb,
    ADD COLUMN IF NOT EXISTS final_summary text,
    ADD COLUMN IF NOT EXISTS graph jsonb;

COMMIT;
