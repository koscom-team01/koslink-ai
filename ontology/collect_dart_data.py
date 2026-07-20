#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - DART 원천 데이터 수집 스크립트

initialize_ontology.py의 51개사 유니버스를 대상으로, Open DART API에서
1) 최신 사업보고서 원문 텍스트, 2) 타법인 출자현황(구조화 데이터)을 수집해
.cache/dart_raw/{ticker}.json 에 회사별로 저장한다.

수집(이 스크립트)과 LLM 추출(extract_relations.py)을 분리해서, LLM 호출
단계에서 문제가 생겨도 DART API를 다시 두드리지 않도록 한다.
"""

import json
import sys
import time
from datetime import date
from pathlib import Path

from dart_client import DartOpenApiClient

from initialize_ontology import STOCKS

OUTPUT_DIR = Path(".cache/dart_raw")


def collect_for_stock(client: DartOpenApiClient, stock: dict) -> dict:
    ticker = stock["ticker"]
    result = {
        "id": stock["id"],
        "name": stock["name"],
        "ticker": ticker,
        "corp_code": None,
        "business_report": None,
        "equity_investments": [],
        "errors": [],
    }

    corp_code = client.resolve_corp_code(ticker)
    if not corp_code:
        result["errors"].append("corp_code를 찾지 못함 (corpCode.xml에 없는 종목코드)")
        return result
    result["corp_code"] = corp_code

    try:
        report = client.get_latest_business_report(corp_code)
        if report:
            text = client.get_business_report_text(report.rcept_no)
            result["business_report"] = {
                "rcept_no": report.rcept_no,
                "report_nm": report.report_nm,
                "rcept_dt": report.rcept_dt,
                "text": text,
            }
        else:
            result["errors"].append("최근 사업보고서를 찾지 못함")
    except Exception as e:
        result["errors"].append(f"사업보고서 수집 실패: {e}")

    this_year = date.today().year
    for bsns_year in (str(this_year - 1), str(this_year - 2)):
        try:
            investments = client.get_equity_investments(corp_code, bsns_year=bsns_year)
        except Exception as e:
            result["errors"].append(f"{bsns_year} 타법인출자현황 조회 실패: {e}")
            continue
        if investments:
            result["equity_investments"] = [inv.model_dump() for inv in investments]
            result["equity_investments_bsns_year"] = bsns_year
            break

    return result


def main() -> None:
    try:
        client = DartOpenApiClient()
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"▶️ {len(STOCKS)}개사 DART 데이터 수집 시작")
    ok, failed = 0, 0
    for i, stock in enumerate(STOCKS, start=1):
        print(f"  [{i}/{len(STOCKS)}] {stock['name']} ({stock['ticker']}) 수집 중...")
        data = collect_for_stock(client, stock)
        out_path = OUTPUT_DIR / f"{stock['ticker']}.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        if data["errors"]:
            failed += 1
            for err in data["errors"]:
                print(f"    ⚠️ {err}")
        else:
            ok += 1
        time.sleep(0.2)  # DART API 예의상 딜레이

    print(f"\n✅ 수집 완료: 성공 {ok}건 / 이슈 있음 {failed}건 → {OUTPUT_DIR}/ 에 저장됨")


if __name__ == "__main__":
    main()
