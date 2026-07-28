#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - 오버나잇 딥리서치(Claude, 51개 유니버스) 결과를 Neo4j에 반영.

.cache/deep_research/research_{ticker}.json 파일들을 읽어 RELATED_TO 엣지로
MERGE한다. 기존 DART 기반 엣지와 같은 DB 안에 있되, extractionMethod:
"Claude_Deep_Research" 태그로 구분해 비교 가능하게 한다.

DART 파이프라인과 달리 회사명 정규화 매칭이 아니라 ticker로 직접 매핑한다
(리서치 결과 JSON이 이름이 아니라 티커를 담고 있어 더 안정적).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from neo4j import GraphDatabase

from config import get_settings
from initialize_ontology import STOCKS

RESEARCH_DIR = Path(".cache/deep_research")
SUMMARY_FILE = RESEARCH_DIR / "ingest_summary.json"

TICKER_TO_ID = {s["ticker"]: s["id"] for s in STOCKS}
TICKER_TO_NAME = {s["ticker"]: s["name"] for s in STOCKS}

MERGE_QUERY = """
MATCH (a:Stock {id: $from_id})
MATCH (b:Stock {id: $to_id})
MERGE (a)-[r:RELATED_TO {relation_type: $relation_type}]->(b)
ON CREATE SET r.firstSeenAt = $now
SET r.description = $description,
    r.direction = $direction,
    r.investorInsight = $investor_insight,
    r.priceRelation = $price_relation,
    r.sourceUrls = $source_urls,
    r.sourceType = $source_type,
    r.confidenceNote = $confidence_note,
    r.fact_source = $fact_source,
    r.confidenceScore = 0.9,
    r.extractionMethod = "Claude_Deep_Research",
    r.status = "VERIFIED",
    r.verifiedBy = "Claude_Deep_Research_Overnight",
    r.verifiedAt = $now
RETURN r.firstSeenAt = $now AS created, a.name AS from_name, b.name AS to_name
"""


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

    files = sorted(RESEARCH_DIR.glob("research_*.json"))
    if not files:
        print(f"❌ {RESEARCH_DIR}/ 에 research_*.json 파일이 없습니다.")
        return

    written, skipped_no_map, skipped_no_relations = 0, 0, 0
    summary_rows: list[dict] = []

    with driver.session() as session:
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            subject_ticker = data.get("target_ticker", "")
            from_id = TICKER_TO_ID.get(subject_ticker)
            from_name = TICKER_TO_NAME.get(subject_ticker, data.get("target_name", subject_ticker))
            if not from_id:
                print(f"  ⚠️ {path.name}: target_ticker '{subject_ticker}' 매핑 실패, 스킵")
                continue

            relations = data.get("relations", [])
            if not relations:
                skipped_no_relations += 1
                continue

            for rel in relations:
                to_ticker = rel.get("target_ticker", "")
                to_id = TICKER_TO_ID.get(to_ticker)
                if not to_id:
                    skipped_no_map += 1
                    continue

                now = datetime.now(timezone.utc).isoformat()
                source_urls = rel.get("source_urls", [])
                result = session.run(
                    MERGE_QUERY,
                    from_id=from_id,
                    to_id=to_id,
                    relation_type=rel["relation_category"],
                    description=rel["description"],
                    direction=rel["direction"],
                    investor_insight=rel["investor_insight"],
                    price_relation=rel["price_relation"],
                    source_urls=source_urls,
                    source_type=rel.get("source_type", ""),
                    confidence_note=rel.get("confidence_note", ""),
                    fact_source=f"Claude 딥리서치{(' - ' + source_urls[0]) if source_urls else ''}",
                    now=now,
                )
                record = result.single()
                if record is None:
                    continue
                written += 1
                summary_rows.append(
                    {
                        "from_ticker": subject_ticker,
                        "from_name": record["from_name"],
                        "to_ticker": to_ticker,
                        "to_name": record["to_name"],
                        "relation_type": rel["relation_category"],
                        "direction": rel["direction"],
                        "price_relation": rel["price_relation"],
                        "description": rel["description"],
                        "investor_insight": rel["investor_insight"],
                        "source_urls": source_urls,
                        "source_type": rel.get("source_type", ""),
                        "confidence_note": rel.get("confidence_note", ""),
                        "created": bool(record["created"]),
                    }
                )

    driver.close()

    SUMMARY_FILE.write_text(json.dumps(summary_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 반영 완료: {written}건 (파일 {len(files)}개 중)")
    print(f"   유니버스 밖 매핑 실패: {skipped_no_map}건, 관계 없음 파일: {skipped_no_relations}개")
    print(f"   요약: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
