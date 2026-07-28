"""51개사 전체: extract_relations.py 로직(OpenAI) + update_graph.py 로직을 회사별로 실행하고
회사별 통계(후보 건수, 토큰, 그래프 반영 건수)를 수집해 리포트용 JSON으로 남긴다.
기존 extract_relations.py / update_graph.py 파일은 건드리지 않고 그 함수들을 그대로 재사용한다.
"""
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import openai
from neo4j import GraphDatabase

from config import get_settings
from extract_relations import RAW_DIR, build_structured_candidates, build_llm_candidates
from update_graph import normalize_name, build_name_index, MERGE_QUERY, CONFIDENCE_BY_METHOD, DEFAULT_LLM_CONFIDENCE
from initialize_ontology import STOCKS

settings = get_settings()
client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
name_index = build_name_index()

raw_files = sorted(RAW_DIR.glob("*.json"))
# STOCKS 순서(원래 51개 순서)대로 처리
ticker_order = {s["ticker"]: i for i, s in enumerate(STOCKS)}
raw_files.sort(key=lambda p: ticker_order.get(p.stem, 999))

all_candidates = []
report_rows = []

with driver.session() as session:
    for i, path in enumerate(raw_files, start=1):
        company = json.loads(path.read_text(encoding="utf-8"))
        name = company["name"]
        ticker = company["ticker"]
        print(f"[{i}/{len(raw_files)}] {name} ({ticker}) 처리 중...", flush=True)

        row = {
            "순번": i, "기업명": name, "티커": ticker,
            "구조화후보": 0, "LLM후보": 0, "입력토큰": 0, "출력토큰": 0,
            "그래프반영": 0, "유니버스밖스킵": 0, "오류": "",
        }

        try:
            structured = build_structured_candidates(company)
        except Exception as e:
            structured = []
            row["오류"] += f"구조화추출실패:{e}; "
        row["구조화후보"] = len(structured)

        usage = {"input_tokens": 0, "output_tokens": 0}
        try:
            llm_candidates = build_llm_candidates(client, settings.OPENAI_MODEL, company, usage)
        except Exception as e:
            llm_candidates = []
            row["오류"] += f"LLM추출실패:{e}; "
        row["LLM후보"] = len(llm_candidates)
        row["입력토큰"] = usage["input_tokens"]
        row["출력토큰"] = usage["output_tokens"]

        company_candidates = structured + llm_candidates
        all_candidates.extend(company_candidates)

        written, skipped = 0, 0
        for cand in company_candidates:
            from_id = name_index.get(normalize_name(cand["from_company"]))
            to_id = name_index.get(normalize_name(cand["to_company"]))
            if not from_id or not to_id:
                skipped += 1
                continue
            now = datetime.now(timezone.utc).isoformat()
            confidence = CONFIDENCE_BY_METHOD.get(cand["extraction_method"], DEFAULT_LLM_CONFIDENCE)
            result = session.run(
                MERGE_QUERY, from_id=from_id, to_id=to_id, relation_type=cand["relation_type"],
                description=cand["description"], source_document_title=cand["source_document_title"],
                source_quote=cand["source_quote"], confidence=confidence,
                extraction_method=cand["extraction_method"], now=now,
            )
            if result.single():
                written += 1
            else:
                skipped += 1
        row["그래프반영"] = written
        row["유니버스밖스킵"] = skipped

        report_rows.append(row)
        time.sleep(0.3)

driver.close()

Path(".cache/relation_candidates.json").write_text(
    json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8"
)
Path("logs/pipeline_run_report.json").write_text(
    json.dumps(report_rows, ensure_ascii=False, indent=2), encoding="utf-8"
)

total_written = sum(r["그래프반영"] for r in report_rows)
total_in = sum(r["입력토큰"] for r in report_rows)
total_out = sum(r["출력토큰"] for r in report_rows)
print(f"\n완료: 총 후보 {len(all_candidates)}건, 그래프 반영 {total_written}건")
print(f"총 토큰: 입력 {total_in:,} / 출력 {total_out:,}")
