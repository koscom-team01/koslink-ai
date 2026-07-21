# shared/dart_client

금융감독원 Open DART API 공용 클라이언트. `ontology/`와 `rag/`가 형제 폴더로
import해서 함께 쓴다 (온톨로지팀의 사업보고서/공시 수집, RAG팀의 뉴스·공시
본문 적재 양쪽에서 재사용 가능).

## 설치

`ontology/requirements.txt`, `rag/requirements.txt` 양쪽에 이미 아래 줄이
들어있어 각자 폴더에서 평소처럼 `pip install -r requirements.txt`만 하면
자동으로 같이 설치된다.

```
-e ../shared
```

## 환경변수

호출하는 쪽(`ontology/.env` 또는 `rag/.env`)에 아래 값이 필요하다.

```
DART_API_KEY=       # https://opendart.fss.or.kr 에서 발급
DART_CACHE_DIR=.cache/dart   # corp_code 매핑 캐시 저장 위치 (기본값)
```

## 사용법

```python
from dart_client import DartOpenApiClient

client = DartOpenApiClient()  # 현재 작업 디렉토리의 .env에서 DART_API_KEY를 읽음

# 1) 종목코드(6자리) -> DART 고유번호(8자리)
corp_code = client.resolve_corp_code("005930")

# 2) 최근 3년 이내 공시 검색
items = client.search_disclosures(corp_code=corp_code, pblntf_ty="A")

# 3) 가장 최근 사업보고서 메타데이터
report = client.get_latest_business_report(corp_code)

# 4) 사업보고서 '사업의 개요' 본문 텍스트 (감사보고서 등 첨부문서 제외, 목차 제외)
text = client.get_business_report_text(report.rcept_no, max_chars=20000)

# 5) 타법인 출자현황 (지분투자 관계 - 구조화 데이터, LLM 불필요)
investments = client.get_equity_investments(corp_code, bsns_year="2025")
```

## 참고

- `resolve_corp_code`는 최초 호출 시 `corpCode.xml`(전체 상장/비상장사 매핑,
  ZIP)을 한 번 받아 `DART_CACHE_DIR/corp_code_map.json`에 캐시해두고 이후에는
  캐시만 읽는다. 캐시가 오래됐다 싶으면 그 파일을 지우고 다시 호출하면 된다.
- 실제 사용 예시는 `ontology/collect_dart_data.py`, `ontology/extract_relations.py`
  참고.
