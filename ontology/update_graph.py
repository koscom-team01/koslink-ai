#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - 그래프 업데이트 스크립트

extract_relations.py가 만든 relation_candidates.json을 읽어, 기존 51개사
유니버스(initialize_ontology.STOCKS) 안에서만 회사명을 Stock id로 매핑한 뒤
RELATED_TO 관계를 Neo4j에 MERGE한다. 유니버스 밖의 상대 회사(자회사, 해외법인
등)로 향하는 후보는 새 노드를 만들지 않고 건너뛴다 (51개사 유니버스 고정 결정).

MERGE로 실제 그래프 변경이 일어날 때마다, Neo4j 안이 아니라 별도 로그 파일
(logs/graph_update_log.jsonl, logs/graph_update_log.md)에 근거를 남긴다.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase

from config import get_settings
from initialize_ontology import STOCKS

CANDIDATES_FILE = Path(".cache/relation_candidates.json")
LOG_DIR = Path("logs")
LOG_JSONL = LOG_DIR / "graph_update_log.jsonl"
LOG_MD = LOG_DIR / "graph_update_log.md"


def normalize_name(name: str) -> str:
    return name.replace("주식회사", "").replace("(주)", "").replace("㈜", "").replace(" ", "").strip()


def build_name_index() -> dict[str, str]:
    """정규화된 회사명 -> Stock id"""
    index = {}
    for stock in STOCKS:
        index[normalize_name(stock["name"])] = stock["id"]
    return index


MERGE_QUERY = """
MATCH (a:Stock {id: $from_id})
MATCH (b:Stock {id: $to_id})
MERGE (a)-[r:RELATED_TO {relation_type: $relation_type}]->(b)
ON CREATE SET r.firstSeenAt = $now
SET r.description = $description,
    r.fact_source = $source_document_title,
    r.source_quote = $source_quote,
    r.confidenceScore = $confidence,
    r.extractionMethod = $extraction_method,
    r.status = "VERIFIED",
    r.verifiedBy = "DART_Learning_Pipeline",
    r.verifiedAt = $now
RETURN r.firstSeenAt = $now AS created, a.name AS from_name, b.name AS to_name
"""

CONFIDENCE_BY_METHOD = {
    "otrCprInvstmntSttus_structured": 0.99,
}
DEFAULT_LLM_CONFIDENCE = 0.85


def main() -> None:
    settings = get_settings()
    if not CANDIDATES_FILE.exists():
        print(f"❌ {CANDIDATES_FILE} 가 없습니다. extract_relations.py를 먼저 실행하세요.")
        return

    candidates = json.loads(CANDIDATES_FILE.read_text(encoding="utf-8"))
    name_index = build_name_index()

    driver = GraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_rows: list[dict] = []
    written, skipped_out_of_universe = 0, 0

    with driver.session() as session, LOG_JSONL.open("a", encoding="utf-8") as jsonl_f:
        for cand in candidates:
            from_id = name_index.get(normalize_name(cand["from_company"]))
            to_id = name_index.get(normalize_name(cand["to_company"]))
            if not from_id or not to_id:
                skipped_out_of_universe += 1
                continue

            now = datetime.now(timezone.utc).isoformat()
            confidence = CONFIDENCE_BY_METHOD.get(cand["extraction_method"], DEFAULT_LLM_CONFIDENCE)

            result = session.run(
                MERGE_QUERY,
                from_id=from_id,
                to_id=to_id,
                relation_type=cand["relation_type"],
                description=cand["description"],
                source_document_title=cand["source_document_title"],
                source_quote=cand["source_quote"],
                confidence=confidence,
                extraction_method=cand["extraction_method"],
                now=now,
            )
            record = result.single()
            if record is None:
                continue

            written += 1
            log_entry = {
                "timestamp": now,
                "target": f"RELATED_TO({cand['relation_type']}): {from_id}({record['from_name']}) -> {to_id}({record['to_name']})",
                "source_document_title": cand["source_document_title"],
                "source_quote": cand["source_quote"],
                "cypher_result": "created" if record["created"] else "updated",
            }
            log_rows.append(log_entry)
            jsonl_f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    driver.close()

    md_lines = [
        "# 그래프 업데이트 근거 로그",
        "",
        "| 시각 | 반영된 노드/엣지 | 결과 | 출처 문서 | 근거 문구 |",
        "|---|---|---|---|---|",
    ]
    for row in log_rows:
        quote = row["source_quote"].replace("|", "\\|").replace("\n", " ")
        md_lines.append(
            f"| {row['timestamp']} | {row['target']} | {row['cypher_result']} | "
            f"{row['source_document_title']} | {quote} |"
        )
    LOG_MD.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(f"✅ 그래프 업데이트 완료: {written}건 반영, {skipped_out_of_universe}건 스킵(유니버스 밖 상대 회사)")
    print(f"   로그: {LOG_JSONL}, {LOG_MD}")


if __name__ == "__main__":
    main()
