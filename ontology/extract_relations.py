#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - 관계 후보 추출 스크립트

collect_dart_data.py가 모아둔 .cache/dart_raw/*.json을 읽어 두 경로로
RELATED_TO 관계 후보를 만든다.

1) 구조화 경로 (LLM 불필요): 타법인출자현황 데이터를 그대로 EQUITY_INVESTMENT로 변환
2) 비구조화 경로 (Claude): 사업보고서 '사업의 개요' 본문에서 관계를 추출

두 경로 모두 후보에 근거(source_document_title, source_quote)를 남긴다.
DB에는 바로 쓰지 않고 .cache/relation_candidates.json에 저장해 검수 후
update_graph.py로 적재한다.
"""

import json
import sys
from pathlib import Path

import openai

from config import get_settings

RAW_DIR = Path(".cache/dart_raw")
OUTPUT_FILE = Path(".cache/relation_candidates.json")

RELATION_TYPES = ["EQUITY_INVESTMENT", "AFFILIATE", "LICENSING", "COMPETITOR", "MNA", "OTHER"]

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "to_company": {"type": "string", "description": "상대 회사의 한글 정식/약식 명칭"},
                    "relation_type": {"type": "string", "enum": RELATION_TYPES},
                    "description": {
                        "type": "string",
                        "description": (
                            "관계를 설명하는 한국어 문장 (100자 내외). 반드시 company_name과 상대 회사 "
                            "이름을 문장에 모두 명시하고, 어느 회사 기준으로 읽어도 자연스러운 객관적 "
                            "3인칭 사실 문장으로 작성할 것 (상대 회사 이름을 생략한 암묵적 주어 금지)."
                        ),
                    },
                    "source_quote": {
                        "type": "string",
                        "description": "이 관계 판단의 근거가 된 원문 문장을 수정 없이 그대로 발췌",
                    },
                },
                "required": ["to_company", "relation_type", "description", "source_quote"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["relations"],
    "additionalProperties": False,
}

PROMPT_TEMPLATE = """아래는 반도체 기업 "{company_name}"의 사업보고서 요약본입니다(LLM이 원문을 요약한 것).
이 요약본에서 {company_name}와(과) 다른 회사 사이의 관계(지분투자/계열사/기술 라이선싱/경쟁사/인수합병 등)를
찾아 JSON으로 추출해 주세요.

규칙:
- relation_type은 반드시 EQUITY_INVESTMENT, AFFILIATE, LICENSING, COMPETITOR, MNA, OTHER 중 하나여야 합니다.
  (공급/거래 관계는 이미 별도 시스템에서 처리하므로 여기서는 추출하지 마세요.)
- source_quote는 반드시 아래 요약본에서 그대로 발췌한 문장이어야 하며(요약본 자체가 근거 문서입니다),
  다시 요약하거나 새로 쓰면 안 됩니다.
- description은 반드시 {company_name}과 상대 회사 이름을 문장 안에 모두 명시하고, 어느 회사 기준으로
  읽어도 자연스러운 객관적 3인칭 사실 문장으로 작성하세요. (예: "OO는 XX와 경쟁 관계인 반도체
  제조사이다" — "상대 회사와 경쟁 관계"처럼 상대 회사 이름을 생략하거나 암묵적 주어로 쓰지 마세요.)
- 요약본에 명확한 관계 언급이 없으면 relations를 빈 배열로 반환하세요. 추측하지 마세요.

[사업보고서 요약본]
{report_text}
"""


def build_structured_candidates(company: dict) -> list[dict]:
    candidates = []
    bsns_year = company.get("equity_investments_bsns_year", "N/A")
    for inv in company.get("equity_investments", []):
        to_company = (inv.get("inv_prm") or "").strip()
        if not to_company:
            continue
        ratio = inv.get("trmend_blce_qota_rt") or "N/A"
        amount = inv.get("trmend_blce_acntbk_amount") or "N/A"
        candidates.append(
            {
                "from_company": company["name"],
                "to_company": to_company,
                "relation_type": "EQUITY_INVESTMENT",
                "description": f"{company['name']}가 {to_company} 지분을 보유 (기말 지분율 {ratio}%, 장부가액 {amount}원)",
                "source_document_title": f"{company['name']} {bsns_year} 사업연도 타법인출자현황",
                "source_quote": (
                    f"inv_prm: {inv.get('inv_prm')}, "
                    f"trmend_blce_qota_rt: {inv.get('trmend_blce_qota_rt')}, "
                    f"trmend_blce_acntbk_amount: {inv.get('trmend_blce_acntbk_amount')}"
                ),
                "extraction_method": "otrCprInvstmntSttus_structured",
            }
        )
    return candidates


def build_llm_candidates(client: openai.OpenAI, model: str, company: dict, usage_totals: dict) -> list[dict]:
    report = company.get("business_report")
    if not report or not report.get("text"):
        return []

    prompt = PROMPT_TEMPLATE.format(company_name=company["name"], report_text=report["text"])
    response = client.chat.completions.create(
        model=model,
        max_tokens=2048,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "relation_extraction", "schema": EXTRACTION_SCHEMA, "strict": True},
        },
        messages=[{"role": "user", "content": prompt}],
    )
    usage_totals["input_tokens"] += response.usage.prompt_tokens
    usage_totals["output_tokens"] += response.usage.completion_tokens

    parsed = json.loads(response.choices[0].message.content)

    source_document_title = f"{report['report_nm']} (rcept_no: {report['rcept_no']})"
    candidates = []
    for rel in parsed.get("relations", []):
        candidates.append(
            {
                "from_company": company["name"],
                "to_company": rel["to_company"],
                "relation_type": rel["relation_type"],
                "description": rel["description"],
                "source_document_title": source_document_title,
                "source_quote": rel["source_quote"],
                "extraction_method": f"openai_{model}",
            }
        )
    return candidates


def main() -> None:
    settings = get_settings()
    raw_files = sorted(RAW_DIR.glob("*.json"))
    if not raw_files:
        print(f"❌ {RAW_DIR}/ 에 수집된 데이터가 없습니다. collect_dart_data.py를 먼저 실행하세요.")
        sys.exit(1)

    client = None
    if settings.OPENAI_API_KEY:
        client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    else:
        print("⚠️  OPENAI_API_KEY가 없어 LLM 추출(비구조화 경로)은 건너뜁니다 — 구조화 경로만 실행합니다.")

    usage_totals = {"input_tokens": 0, "output_tokens": 0}
    all_candidates: list[dict] = []

    for i, path in enumerate(raw_files, start=1):
        company = json.loads(path.read_text(encoding="utf-8"))
        print(f"  [{i}/{len(raw_files)}] {company['name']} 관계 추출 중...")

        all_candidates.extend(build_structured_candidates(company))

        if client:
            try:
                all_candidates.extend(
                    build_llm_candidates(client, settings.OPENAI_MODEL, company, usage_totals)
                )
            except Exception as e:
                print(f"    ⚠️ LLM 추출 실패: {e}")

    OUTPUT_FILE.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n✅ 관계 후보 {len(all_candidates)}건 → {OUTPUT_FILE}")
    if client:
        total = usage_totals["input_tokens"] + usage_totals["output_tokens"]
        print(
            f"   OpenAI 사용량: 입력 {usage_totals['input_tokens']:,} + "
            f"출력 {usage_totals['output_tokens']:,} = 총 {total:,} 토큰"
        )


if __name__ == "__main__":
    main()
