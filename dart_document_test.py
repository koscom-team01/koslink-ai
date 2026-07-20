#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
kosLINK AI - DART Document Retrieval Test Script (Robust Error Diagnosis Version)
Open DART API를 사용하여 공시 접수번호를 조회하고, 실제 보고서 HTML 압축파일을 내려받아 내용을 검증하는 테스트 코드입니다.
DART 방화벽 차단을 우회하기 위한 User-Agent 헤더 추가 및 에러 디버깅 정보 출력이 강화되었습니다.
"""

import os
import zipfile
import io
import requests
from bs4 import BeautifulSoup

def test_dart_document_retrieval(api_key, ticker):
    print("=" * 60)
    print(f"🔍 [1단계] Ticker {ticker}의 최근 사업보고서(공시) 접수번호 조회 중...")
    print("=" * 60)
    
    list_url = "https://opendart.fss.or.kr/api/list.json"
    params = {
        "auth": api_key,
        "stock_code": ticker,
        "pblntf_ty": "A",  # A: 사업보고서, B: 반기보고서, C: 분기보고서
        "bgn_de": "20240101",
        "page_no": "1",
        "page_count": "5"
    }
    
    # DART 방화벽 우회용 표준 브라우저 User-Agent 주입
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        res = requests.get(list_url, params=params, headers=headers, timeout=5)
        
        # HTTP 응답 상태코드 검증
        if res.status_code != 200:
            print(f"  ❌ DART 서버가 HTTP 에러 코드를 반환했습니다: {res.status_code}")
            print(f"  └ 응답 본문 미리보기: {res.text[:300]}")
            return
            
        # JSON 해석 시도 및 예외처리 강화
        try:
            data = res.json()
        except ValueError as json_err:
            print("  ❌ DART 응답이 JSON 형식이 아닙니다 (파싱 에러).")
            print("  └ DART가 반환한 실제 데이터 (대부분 API Key 오류 혹은 접속제한 HTML 페이지):")
            print("-" * 50)
            print(res.text[:500].strip())
            print("-" * 50)
            return
        
        if data.get("status") != "000":
            print(f"  ❌ DART API 오류 반환:")
            print(f"    - 상태코드: {data.get('status')}")
            print(f"    - 메시지: {data.get('message')}")
            return
            
        disclosures = data.get("list", [])
        if not disclosures:
            print("  ❌ 해당 조건에 맞는 공시 보고서가 없습니다.")
            return
            
        latest_report = disclosures[0]
        rcept_no = latest_report["rcept_no"]
        report_title = latest_report["report_nm"]
        submitter = latest_report["corp_nm"]
        submit_date = latest_report["rcept_dt"]
        
        print(f"  🟢 공시 검색 성공!")
        print(f"    - 회사명: {submitter}")
        print(f"    - 보고서명: {report_title}")
        print(f"    - 접수번호(rcept_no): {rcept_no}")
        print(f"    - 공시 접수일: {submit_date}")
        
    except Exception as e:
        print(f"  ❌ DART API 요청 중 일반 네트워크 오류 발생: {e}")
        return

    print("\n" + "=" * 60)
    print(f"📥 [2단계] 접수번호 {rcept_no}의 원본 HTML 문서 파일(ZIP) 다운로드 중...")
    print("=" * 60)

    doc_url = "https://opendart.fss.or.kr/api/document.xml"
    doc_params = {
        "auth": api_key,
        "rcept_no": rcept_no
    }
    
    try:
        doc_res = requests.get(doc_url, params=doc_params, headers=headers, timeout=10)
        doc_res.raise_for_status()
        
        if b"<status>" in doc_res.content[:100]:
            soup = BeautifulSoup(doc_res.content, "xml")
            print(f"  ❌ 문서 다운로드 실패: {soup.find('message').text}")
            return
            
        print(f"  🟢 ZIP 파일 다운로드 완료! (용량: {len(doc_res.content):,} bytes)")
        
        with zipfile.ZipFile(io.BytesIO(doc_res.content)) as zip_file:
            file_list = zip_file.namelist()
            print(f"  🟢 압축파일 내부 HTML 문서 목록 (총 {len(file_list)}개):")
            for filename in file_list[:5]:
                print(f"    - {filename}")
            if len(file_list) > 5:
                print(f"    - ... (외 {len(file_list) - 5}개 파일 더 있음)")
                
            largest_file = max(file_list, key=lambda f: zip_file.getinfo(f).file_size)
            print(f"\n🔬 [3단계] 가장 큰 파일인 '{largest_file}'의 내용 추출 시도...")
            
            with zip_file.open(largest_file) as f:
                raw_html = f.read()
                try:
                    html_text = raw_html.decode("utf-8")
                except UnicodeDecodeError:
                    html_text = raw_html.decode("cp949")
                
                soup = BeautifulSoup(html_text, "lxml")
                plain_text = soup.get_text(separator="\n")
                cleaned_text = "\n".join([line.strip() for line in plain_text.splitlines() if line.strip()])
                
                print(f"  🟢 파일 해석 성공! 앞부분 500글자 본문 미리보기:")
                print("-" * 50)
                print(cleaned_text[:500] + "\n...")
                print("-" * 50)
                
    except Exception as e:
        print(f"  ❌ 문서 다운로드 및 압축 해제 중 오류 발생: {e}")

if __name__ == "__main__":
    DART_API_KEY = os.environ.get("DART_API_KEY", "YOUR_DART_API_KEY_HERE")
    TICKER = "042700" 
    
    if DART_API_KEY == "YOUR_DART_API_KEY_HERE":
        print("💡 [입력 필요] DART_API_KEY 환경변수가 설정되지 않았습니다.")
        print("   스크립트 하단의 'YOUR_DART_API_KEY_HERE' 문구를 본인의 Open DART API 키로 수정해 주세요.")
    else:
        test_dart_document_retrieval(DART_API_KEY, TICKER)