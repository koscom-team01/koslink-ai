import io
import json
import warnings
import zipfile
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .config import DartSettings, get_dart_settings
from .models import DisclosureItem, EquityInvestment

# DART 원본 문서는 정상 XML이 아닌 경우가 잦아(중첩된 HTML 엔티티 등)
# 엄격한 XML 파서 대신 관대한 lxml HTML 파서로 의도적으로 처리한다.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

BASE_URL = "https://opendart.fss.or.kr/api"


class DartOpenApiClient:
    def __init__(self, settings: Optional[DartSettings] = None):
        self.settings = settings or get_dart_settings()
        if not self.settings.DART_API_KEY:
            raise ValueError("DART_API_KEY가 설정되지 않았습니다 (.env 확인)")
        self._cache_dir = Path(self.settings.DART_CACHE_DIR)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._corp_code_map: Optional[dict[str, str]] = None

    def _get(self, path: str, **params) -> requests.Response:
        params["crtfc_key"] = self.settings.DART_API_KEY
        res = requests.get(f"{BASE_URL}/{path}", params=params, timeout=15)
        res.raise_for_status()
        return res

    # ------------------------------------------------------------------
    # 고유번호(corp_code) 매핑
    # ------------------------------------------------------------------
    def _load_corp_code_map(self) -> dict[str, str]:
        cache_file = self._cache_dir / "corp_code_map.json"
        if cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8"))

        res = self._get("corpCode.xml")
        zf = zipfile.ZipFile(io.BytesIO(res.content))
        xml_bytes = zf.read("CORPCODE.xml")
        soup = BeautifulSoup(xml_bytes, "xml")

        ticker_to_corp_code: dict[str, str] = {}
        for item in soup.find_all("list"):
            stock_code = (item.find("stock_code").text or "").strip()
            corp_code = (item.find("corp_code").text or "").strip()
            if stock_code:
                ticker_to_corp_code[stock_code] = corp_code

        cache_file.write_text(
            json.dumps(ticker_to_corp_code, ensure_ascii=False), encoding="utf-8"
        )
        return ticker_to_corp_code

    def resolve_corp_code(self, ticker: str) -> Optional[str]:
        if self._corp_code_map is None:
            self._corp_code_map = self._load_corp_code_map()
        return self._corp_code_map.get(ticker)

    # ------------------------------------------------------------------
    # 공시검색
    # ------------------------------------------------------------------
    def search_disclosures(
        self,
        corp_code: Optional[str] = None,
        bgn_de: Optional[str] = None,
        end_de: Optional[str] = None,
        pblntf_ty: Optional[str] = None,
        pblntf_detail_ty: Optional[str] = None,
        last_reprt_at: str = "Y",
        page_count: int = 100,
    ) -> list[DisclosureItem]:
        params = {
            "page_count": page_count,
            "last_reprt_at": last_reprt_at,
        }
        if corp_code:
            params["corp_code"] = corp_code
        if bgn_de:
            params["bgn_de"] = bgn_de
        if end_de:
            params["end_de"] = end_de
        if pblntf_ty:
            params["pblntf_ty"] = pblntf_ty
        if pblntf_detail_ty:
            params["pblntf_detail_ty"] = pblntf_detail_ty

        res = self._get("list.json", **params)
        data = res.json()
        if data.get("status") != "000":
            return []
        return [DisclosureItem(**item) for item in data.get("list", [])]

    def get_latest_business_report(self, corp_code: str) -> Optional[DisclosureItem]:
        """최근 접수된 사업보고서(정기공시 A유형) 1건을 반환한다.

        list.json은 bgn_de/end_de를 생략하면 최근 며칠로 검색 범위가 좁혀지므로,
        연 1회만 발행되는 사업보고서를 찾으려면 명시적으로 넓은 기간을 지정해야 한다.
        """
        end_de = date.today().strftime("%Y%m%d")
        bgn_de = (date.today() - timedelta(days=3 * 365)).strftime("%Y%m%d")
        items = self.search_disclosures(
            corp_code=corp_code, pblntf_ty="A", bgn_de=bgn_de, end_de=end_de
        )
        for item in items:
            if item.report_nm and "사업보고서" in item.report_nm:
                return item
        return None

    # ------------------------------------------------------------------
    # 원본 문서 텍스트
    # ------------------------------------------------------------------
    def _extract_zip_text(self, rcept_no: str) -> str:
        """document.xml(ZIP)을 다운로드해 본문 텍스트를 이어붙여 반환한다.

        ZIP 안에는 공시 본문(`{rcept_no}.xml`) 외에 감사보고서 등 별도
        첨부문서가 함께 들어있는 경우가 많아, 본문 파일만 골라서 사용한다.
        """
        res = self._get("document.xml", rcept_no=rcept_no)
        zf = zipfile.ZipFile(io.BytesIO(res.content))

        main_name = f"{rcept_no}.xml"
        member_names = [main_name] if main_name in zf.namelist() else zf.namelist()

        chunks: list[str] = []
        for name in member_names:
            raw = zf.read(name)
            soup = BeautifulSoup(raw, "lxml")
            chunks.append(soup.get_text(separator="\n"))

        full_text = "\n".join(chunks)
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        return "\n".join(lines)

    def get_business_report_text(self, rcept_no: str, max_chars: int = 20000) -> str:
        """사업보고서 본문에서 '사업의 개요' 절만 잘라 반환한다.

        본문 파일 앞부분은 목차라 "사업의 개요"가 최소 2번(목차 항목 + 실제
        섹션 제목) 등장하는데, 관계·거래처 관련 서술은 실제 섹션(마지막 등장
        위치)부터 시작하므로 그 지점부터 잘라낸다.
        """
        cleaned = self._extract_zip_text(rcept_no)

        marker = "사업의 개요"
        last_idx = cleaned.rfind(marker)
        if last_idx != -1:
            cleaned = cleaned[last_idx:]

        return cleaned[:max_chars]

    def get_disclosure_document_text(self, rcept_no: str, max_chars: int = 4000) -> str:
        """단일판매·공급계약체결 등 일반 공시 본문 텍스트를 그대로 반환한다.

        사업보고서와 달리 정형화된 절 구분이 없어 별도 절단 없이 앞부분만 자른다.
        """
        return self._extract_zip_text(rcept_no)[:max_chars]

    # ------------------------------------------------------------------
    # 타법인 출자현황 (구조화, LLM 불필요)
    # ------------------------------------------------------------------
    def get_equity_investments(
        self, corp_code: str, bsns_year: str, reprt_code: str = "11011"
    ) -> list[EquityInvestment]:
        res = self._get(
            "otrCprInvstmntSttus.json",
            corp_code=corp_code,
            bsns_year=bsns_year,
            reprt_code=reprt_code,
        )
        data = res.json()
        if data.get("status") != "000":
            return []
        return [EquityInvestment(**item) for item in data.get("list", [])]
