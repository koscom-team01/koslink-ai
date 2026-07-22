"""대상 51개 기업의 최신 사업보고서를 DART에서 받아와 disclosures 테이블에 적재.

vector DB 임베딩은 하지 않음 (원문 텍스트 캐싱까지만). 임베딩은 이후
ingestion_service.py/preload_corpus.py 단계에서 disclosures.raw_text를
읽어 처리한다.

실행: connect_db.sh 로 터널을 연 뒤
    rag/.venv/Scripts/python.exe rag/scripts/fetch_business_reports.py
"""

import os

import psycopg
from dotenv import load_dotenv

from dart_client import DartOpenApiClient

load_dotenv()

PG_DSN = os.environ.get(
    "PG_CONNECTION_STRING",
    "postgresql://admin:adminpassword@localhost:5432/koscomdb",
).replace("postgresql+psycopg://", "postgresql://")


def main() -> None:
    client = DartOpenApiClient()
    conn = psycopg.connect(PG_DSN, autocommit=True)
    cur = conn.cursor()

    cur.execute(
        "SELECT ticker, corp_code, name FROM companies WHERE corp_code IS NOT NULL ORDER BY ticker;"
    )
    companies = cur.fetchall()

    ok, no_report, failed = 0, [], []
    for ticker, corp_code, name in companies:
        try:
            report = client.get_latest_business_report(corp_code)
            if report is None or not report.rcept_no:
                no_report.append((ticker, name))
                continue

            text = client.get_business_report_text(report.rcept_no, max_chars=50000)
            rcept_dt = None
            if report.rcept_dt and len(report.rcept_dt) == 8:
                rcept_dt = f"{report.rcept_dt[:4]}-{report.rcept_dt[4:6]}-{report.rcept_dt[6:]}"
            source_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={report.rcept_no}"

            cur.execute(
                """
                INSERT INTO disclosures (rcept_no, corp_code, report_nm, rcept_dt, raw_text, source_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (rcept_no) DO NOTHING
                """,
                (report.rcept_no, corp_code, report.report_nm, rcept_dt, text, source_url),
            )
            ok += 1
            print(f"OK  {ticker} {name} -> {report.rcept_no} ({len(text)}자)")
        except Exception as e:  # noqa: BLE001 - 스크립트 단계라 개별 기업 실패는 로그만 남기고 계속
            failed.append((ticker, name, str(e)))
            print(f"FAIL {ticker} {name}: {e}")

    conn.close()

    print(f"\n총 {len(companies)}개 중 적재 {ok}건, 사업보고서 없음 {len(no_report)}건, 실패 {len(failed)}건")
    if no_report:
        print("사업보고서 없음:", no_report)
    if failed:
        print("실패:", failed)


if __name__ == "__main__":
    main()
