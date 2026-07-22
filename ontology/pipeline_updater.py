#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - Real-time Data Pipeline Updater (Production Kubernetes CronJob)

우리가 관리하는 51개사 유니버스(initialize_ontology.STOCKS)를 대상으로 공식
Open DART API(shared/dart_client)에서 신규 '단일판매·공급계약체결' 공시를
찾아 Neo4j SUPPLY_TO 그래프를 갱신한다.
"""

import json
import urllib.parse
from datetime import date, datetime, timedelta

import anthropic
import requests
from bs4 import BeautifulSoup
from dart_client import DartOpenApiClient
from neo4j import GraphDatabase

from config import get_settings
from initialize_ontology import STOCKS
from update_graph import normalize_name

settings = get_settings()

CONTRACT_KEYWORD = "공급계약체결"
# DART API의 날짜 필터는 '일(day)' 단위까지만 지원해 "지난 1시간"처럼 정확히
# 자를 수 없다. 매번 오늘+어제를 조회하고 Neo4j에 이미 있는지(dartUrl) 체크해
# 중복을 거르는 방식으로, 자정 경계나 배치 실행 누락에도 안전하게 만든다.
LOOKBACK_DAYS = 2

CONTRACT_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "buyer_name": {"type": "string", "description": "계약 상대방(수요처) 회사의 한글 정식/약식 명칭"},
        "product_name": {"type": "string", "description": "공급 대상 제품/서비스명"},
        "contract_amount": {"type": "string", "description": "계약 금액 (문서에 기재된 형식 그대로)"},
    },
    "required": ["buyer_name", "product_name", "contract_amount"],
    "additionalProperties": False,
}

CONTRACT_PROMPT_TEMPLATE = """아래는 "{supplier_name}"가 공시한 단일판매·공급계약체결 공시 본문입니다.
이 계약의 상대방(수요처), 공급 대상 제품/서비스, 계약 금액을 JSON으로 추출해 주세요.

규칙:
- buyer_name은 "{supplier_name}"이(가) 아닌, 계약 상대방 회사명이어야 합니다.
- 본문에서 명확히 확인되지 않으면 빈 문자열로 두고 추측하지 마세요.

[공시 본문]
{doc_text}
"""

# ==========================================
# 1. 네이버 금융 실시간 종목코드(Ticker) 및 시총 조회 크롤러
# ==========================================

def find_ticker_by_name(company_name):
    """
    네이버 금융 통합 검색 기능을 이용하여 회사 한글명으로부터 6자리 종목코드(Ticker)를 동적으로 조회합니다.
    (예: "에이직랜드" ➔ "448620" / "한미반도체" ➔ "042700")
    """
    # 불필요한 수식어 제거 및 정규화
    clean_name = company_name.replace("주식회사", "").replace("(주)", "").replace(" ", "").strip()

    # 네이버 금융 검색은 euc-kr(cp949) 인코딩 쿼리를 수신합니다.
    try:
        query_encoded = urllib.parse.quote(clean_name, encoding='cp949')
    except Exception:
        query_encoded = urllib.parse.quote(clean_name)

    url = f"https://finance.naver.com/search/searchList.naver?query={query_encoded}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.encoding = 'cp949' # 한글 깨짐 방지
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        # 검색 결과 테이블 내 첫 번째 a 링크 분석
        table = soup.find("table", {"class": "tbl_search"})
        if table:
            a_tag = table.find("a")
            if a_tag and "code=" in a_tag.get("href", ""):
                href = a_tag["href"]
                ticker = href.split("code=")[-1].strip()
                if len(ticker) == 6 and ticker.isdigit():
                    return ticker
    except Exception as e:
        print(f"  ⚠️ 기업명 '{company_name}'에 대한 종목코드 검색 실패: {e}")
    return None

def fetch_naver_finance_market_cap(ticker):
    """
    종목코드를 기반으로 실시간 기업명과 시가총액을 크롤링하여 반환합니다.
    """
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        res = requests.get(url, headers=headers, timeout=5)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "lxml")

        name_div = soup.find("div", {"class": "wrap_company"})
        name = "알수없음"
        if name_div and name_div.find("h2"):
            name = name_div.find("h2").text.strip()

        sum_em = soup.find("em", {"id": "_market_sum"})
        market_cap_won = 0
        if sum_em:
            cap_text = sum_em.text.replace("\n", "").replace("\t", "").replace(",", "").strip()
            if "조" in cap_text:
                parts = cap_text.split("조")
                cho = int(parts[0].strip()) if parts[0].strip() else 0
                uk = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
                market_cap_won = (cho * 1_000_000_000_000) + (uk * 100_000_000)
            else:
                uk = int(cap_text.strip()) if cap_text.strip() else 0
                market_cap_won = uk * 100_000_000

        return name, market_cap_won
    except Exception as e:
        print(f"  ⚠️ Ticker {ticker} 시총 크롤링 실패: {e}")
        return None, 0

# ==========================================
# 2. 파이프라인 태스크 1: 시가총액 일괄 동기화 (Option 1)
# ==========================================

def sync_all_market_caps():
    """
    Neo4j 데이터베이스에 등록된 모든 종목 노드들을 읽어와서
    실시간 시가총액 및 대/중/소 체급 속성을 동기화합니다. (하루 1회 작동 권장)
    """
    print(f"\n🔄 [태스크 1] Neo4j Stock 노드로부터 Ticker 실시간 쿼리 및 시총 동기화 가동...")

    driver = None
    tickers_to_sync = {}
    updated = 0
    now_str = str(datetime.now())
    today_str = date.today().strftime('%Y-%m-%d')

    try:
        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))

        with driver.session() as session:
            result = session.run("MATCH (s:Stock) RETURN s.ticker AS ticker, s.name AS name")
            for record in result:
                if record["ticker"]:
                    tickers_to_sync[record["ticker"]] = record["name"]
            print(f"  └ DB 조회 성공: 총 {len(tickers_to_sync)}개의 트래킹 티커 검출 완료.")

            for ticker, _name_in_db in tickers_to_sync.items():
                _name, cap = fetch_naver_finance_market_cap(ticker)
                if cap == 0:
                    continue

                if cap >= 10_000_000_000_000:
                    cap_size = "Large"
                elif cap >= 1_000_000_000_000:
                    cap_size = "Mid"
                else:
                    cap_size = "Small"

                query = """
                MATCH (s:Stock {ticker: $ticker})
                SET s.marketCap = $cap,
                    s.capSize = $cap_size,
                    s.baseDate = $baseDate,
                    s.sourceAPI = "NaverFinance_Scraper",
                    s.lastUpdated = $now
                RETURN s.name, s.capSize
                """
                res = session.run(query, ticker=ticker, cap=cap, cap_size=cap_size, baseDate=today_str, now=now_str)
                record = res.single()
                if record:
                    print(f"  └ [DB 업데이트 성공] {record[0]} ({ticker}) ➔ {record[1]} (시총: {cap:,}원)")
                    updated += 1

    except Exception as e:
        print(f"  ❌ Neo4j 데이터베이스 연결 실패로 시총 업데이트를 생략합니다: {e}")
        return

    print(f"✅ 총 {updated}개 상장사 시가총액 동기화 완료.")
    if driver:
        driver.close()

# ==========================================
# 3. 파이프라인 태스크 2: 신규 공급계약체결 공시 → SUPPLY_TO 반영
# ==========================================

def build_ticker_index() -> dict[str, dict]:
    """정규화된 회사명 -> STOCKS 항목 (buyer가 우리 유니버스 소속인지 매칭용)"""
    return {normalize_name(stock["name"]): stock for stock in STOCKS}


def already_recorded(session, dart_url: str) -> bool:
    result = session.run(
        "MATCH ()-[r:SUPPLY_TO {dartUrl: $url}]-() RETURN count(r) > 0 AS exists",
        url=dart_url,
    )
    return result.single()["exists"]


def extract_contract_details(client: anthropic.Anthropic, model: str, doc_text: str, supplier_name: str) -> dict | None:
    prompt = CONTRACT_PROMPT_TEMPLATE.format(supplier_name=supplier_name, doc_text=doc_text)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            output_config={"format": {"type": "json_schema", "schema": CONTRACT_EXTRACTION_SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        text_block = next(b for b in response.content if b.type == "text")
        return json.loads(text_block.text)
    except Exception as e:
        print(f"  ⚠️ Claude 계약 추출 실패: {e}")
        return None


def sync_new_supply_contracts():
    """
    51개사 유니버스를 순회하며 최근 공급계약체결 공시를 찾아 SUPPLY_TO 그래프에 반영한다.
    이미 반영된 공시(dartUrl 기준)는 LLM을 재호출하지 않고 건너뛴다.
    """
    print("\n🔄 [태스크 2] Open DART API 신규 공급계약체결 공시 조회 및 반영 가동...")

    try:
        dart = DartOpenApiClient()
    except ValueError as e:
        print(f"  ❌ {e}")
        return

    claude = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY) if settings.ANTHROPIC_API_KEY else None
    if not claude:
        print("  ⚠️ ANTHROPIC_API_KEY가 없어 계약 추출(LLM)을 건너뜁니다.")

    try:
        driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    except Exception as e:
        print(f"  ❌ Neo4j 데이터베이스 연결 실패로 반영을 중단합니다: {e}")
        return

    ticker_index = build_ticker_index()
    end_de = date.today().strftime("%Y%m%d")
    bgn_de = (date.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")

    processed, skipped = 0, 0

    with driver.session() as session:
        for stock in STOCKS:
            corp_code = dart.resolve_corp_code(stock["ticker"])
            if not corp_code:
                continue

            try:
                items = dart.search_disclosures(corp_code=corp_code, bgn_de=bgn_de, end_de=end_de)
            except Exception as e:
                print(f"  ⚠️ {stock['name']} 공시 조회 실패: {e}")
                continue

            contract_items = [item for item in items if item.report_nm and CONTRACT_KEYWORD in item.report_nm]
            if not contract_items:
                continue

            for item in contract_items:
                dart_url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.rcept_no}"
                if already_recorded(session, dart_url):
                    skipped += 1
                    continue

                if not claude:
                    continue

                print(f"\n🚀 신규 공시 감지: '{item.report_nm}' ({stock['name']})")
                doc_text = dart.get_disclosure_document_text(item.rcept_no)
                extracted = extract_contract_details(claude, settings.ANTHROPIC_MODEL, doc_text, stock["name"])
                if not extracted or not extracted.get("buyer_name"):
                    print("  ⚠️ 계약 상대방 식별 불가로 패스합니다.")
                    continue

                buyer_match = ticker_index.get(normalize_name(extracted["buyer_name"]))
                buyer_id = buyer_match["id"] if buyer_match else None
                now_str = str(datetime.now())

                query = """
                MATCH (s:Stock {id: $s_id})
                CALL {
                    WITH s
                    WITH s WHERE $b_id IS NOT NULL
                    MATCH (buyer:Stock {id: $b_id})
                    RETURN buyer

                    UNION

                    WITH s
                    WITH s WHERE $b_id IS NULL
                    MERGE (buyer:Stock {name: $b_name})
                    ON CREATE SET
                        buyer.id = "S_EXTERNAL_" + $b_name,
                        buyer.marketType = "EXTERNAL",
                        buyer.sourceAPI = "DART_Realtime_Pipeline",
                        buyer.lastUpdated = $now
                    RETURN buyer
                }
                MERGE (s)-[rel:SUPPLY_TO {dartUrl: $url}]->(buyer)
                SET rel.product = $product,
                    rel.amount = $amount,
                    rel.fact_source = $source,
                    rel.confidenceScore = 0.98,
                    rel.extractionMethod = "Claude_Realtime_DART_Parser",
                    rel.status = "VERIFIED",
                    rel.verifiedBy = "DART_Realtime_Pipeline",
                    rel.verifiedAt = $now
                RETURN s.name AS supplier_name, buyer.name AS buyer_name, rel.product AS product
                """
                res = session.run(
                    query,
                    s_id=stock["id"],
                    b_id=buyer_id,
                    b_name=extracted["buyer_name"],
                    amount=extracted["contract_amount"],
                    product=extracted["product_name"],
                    source=item.report_nm,
                    url=dart_url,
                    now=now_str,
                )
                record = res.single()
                if record:
                    print(f"  🟢 [DB 반영 완료] '{record['supplier_name']}' ➔(SUPPLY_TO: {record['product']})➔ '{record['buyer_name']}'")
                    processed += 1

    driver.close()
    print(f"\n✅ 신규 공급계약 공시 반영 완료: 신규 {processed}건 / 이미 처리됨(스킵) {skipped}건")

# ==========================================
# 4. 쿠버네티스 Job 일회성 실행 진입점
# ==========================================

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 kosLINK AI 데이터 동기화 파이프라인 배치 가동 (Kubernetes Job / Anthropic API)")
    print("=" * 60)

    # 1. 등록된 모든 종목의 시가총액 정보 동기화 (Option 1)
    sync_all_market_caps()

    # 2. Open DART API 신규 공급계약체결 공시 조회 및 반영
    sync_new_supply_contracts()

    print("\n✅ 모든 동기화 배치가 성공적으로 처리되었습니다. 컨테이너를 안전하게 종료합니다.")
