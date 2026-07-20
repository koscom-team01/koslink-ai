#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - API & XML Data Extraction Test Script (53-Stock Scale)
금융 데이터 적재 파이프라인의 실 수집 로직(네이버 금융 실시간 크롤링 및 DART 공개 RSS 피드)을 검증하는 독립 테스트 코드입니다.
"""

import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import requests
from datetime import datetime

# ==========================================
# 1. 네이버 금융 실시간 스크래핑 테스트 (Key 필요 없음)
# ==========================================

def fetch_naver_finance_market_cap(ticker):
    """
    네이버 금융에서 종목코드의 실시간 종가명과 시가총액을 추출합니다.
    """
    url = f"https://finance.naver.com/item/main.naver?code={ticker}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    res = requests.get(url, headers=headers, timeout=5)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "lxml")
    
    # 1. 기업명 추출
    name_div = soup.find("div", {"class": "wrap_company"})
    name = "알수없음"
    if name_div and name_div.find("h2"):
        name = name_div.find("h2").text.strip()
        
    # 2. 시가총액 추출
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

def test_live_naver_finance():
    print("\n🔬 [테스트 1] 네이버 금융 실시간 크롤러 작동 검증 (샘플 3개 종목)...")
    sample_tickers = ["005930", "058470", "394280"] # 삼성전자, 리노공업, 오픈엣지
    
    for ticker in sample_tickers:
        name, cap = fetch_naver_finance_market_cap(ticker)
        if cap > 0:
            cap_size = "Large" if cap >= 10_000_000_000_000 else ("Mid" if cap >= 1_000_000_000_000 else "Small")
            print(f"  🟢 크롤링 수신 완료 - {name} ({ticker}):")
            print(f"    - 시가총액: {cap:,} 원")
            print(f"    - 연산된 체급: {cap_size}")
        else:
            print(f"  ❌ {ticker} 크롤링 데이터 없음.")

# ==========================================
# 2. 금감원 DART 공개 RSS 피드 파싱 테스트
# ==========================================

def test_live_dart_rss():
    print("\n🔬 [테스트 2] 금감원 DART 공개 실시간 RSS 피드 크롤러 작동 검증...")
    rss_url = "https://dart.fss.or.kr/api/todayRSS.xml"
    
    try:
        print(f"  └ HTTP GET 요청 발송: {rss_url}")
        res = requests.get(rss_url, timeout=5)
        res.raise_for_status()
        
        soup = BeautifulSoup(res.text, "xml")
        items = soup.find_all("item")
        
        print(f"  🟢 DART RSS 피드 수신 성공. (오늘 총 공시 건수: {len(items)}건)")
        
        # 상위 5개 공시 내용 출력해보기
        print("  [오늘 제출된 공시 헤드라인 상위 5건]")
        for i, item in enumerate(items[:5]):
            title = item.find("title").text if item.find("title") else "제목 없음"
            link = item.find("link").text if item.find("link") else "링크 없음"
            print(f"    {i+1}. {title}")
            
    except Exception as e:
        print(f"  ⚠️ DART RSS 실네트워크 연동 실패 (네트워크 차단 등): {e}")

# ==========================================
# 3. DART 단일공급계약 XML 상세 파싱 검증 (Mock 데이터 활용)
# ==========================================

SAMPLE_DART_XML = """<?xml version="1.0" encoding="UTF-8"?>
<document>
    <title>단일판매ㆍ공급계약체결</title>
    <contract_info>
        <item id="1"><name>공시회사</name><value>에이직랜드 주식회사</value></item>
        <item id="2"><name>계약상대방</name><value>삼성전자 주식회사</value></item>
        <item id="3"><name>계약내용</name><value>2.5D 패키징 및 디자인 서비스 공급 계약</value></item>
        <item id="4"><name>계약금액(원)</name><value>6,500,000,000</value></item>
        <item id="5"><name>최근매출액(원)</name><value>73,000,000,000</value></item>
        <item id="6"><name>매출액대비(%)</name><value>8.9</value></item>
    </contract_info>
</document>
"""

def test_dart_xml_parsing():
    print("\n🔬 [테스트 3] 단일판매 공급 계약 공시 상세 XML 본문 구조 정형 파싱 테스트...")
    try:
        root = ET.fromstring(SAMPLE_DART_XML)
        data = {}
        for item in root.findall(".//item"):
            name = item.find("name").text
            val = item.find("value").text
            
            if name == "공시회사":
                data["supplier"] = val.replace(" 주식회사", "").strip()
            elif name == "계약상대방":
                data["buyer"] = val.replace(" 주식회사", "").replace("주식회사 ", "").strip()
            elif name == "계약내용":
                data["product"] = val
            elif name == "계약금액(원)":
                amount_int = int(val.replace(",", ""))
                data["amount"] = f"{amount_int // 100_000_000}억 원"
            elif name == "매출액대비(%)":
                data["ratio"] = f"{val}%"

        print("  🟢 상세 규격 적출 완료:")
        print(f"    - 공급사(Supplier): {data.get('supplier')}")
        print(f"    - 수요처(Buyer)   : {data.get('buyer')}")
        print(f"    - 제품명(Product) : {data.get('product')}")
        print(f"    - 계약액(Amount)  : {data.get('amount')}")
        print(f"    - 비율(Ratio)     : {data.get('ratio')}")
        
    except Exception as e:
        print(f"  ❌ XML 파싱 에러: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("🧪 kosLINK AI 실시간 데이터 수집 수단 사전 검증 (53-Stock)")
    print("=" * 60)
    test_live_naver_finance()
    test_live_dart_rss()
    test_dart_xml_parsing()
    print("\n✅ 사전 검증 완료.")
