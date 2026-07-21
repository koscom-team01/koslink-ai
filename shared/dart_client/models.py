from typing import Optional

from pydantic import BaseModel


class DisclosureItem(BaseModel):
    """단건 공시 (list.json 응답의 list[] 항목)"""

    corp_cls: Optional[str] = None
    corp_name: Optional[str] = None
    corp_code: Optional[str] = None
    stock_code: Optional[str] = None
    report_nm: Optional[str] = None
    rcept_no: Optional[str] = None
    flr_nm: Optional[str] = None
    rcept_dt: Optional[str] = None
    rm: Optional[str] = None


class EquityInvestment(BaseModel):
    """타법인 출자현황 (otrCprInvstmntSttus.json 응답 항목)"""

    corp_code: Optional[str] = None
    corp_name: Optional[str] = None
    inv_prm: Optional[str] = None  # 법인명(피투자회사)
    frst_acqs_de: Optional[str] = None  # 최초 취득일자
    invstmnt_purps: Optional[str] = None  # 출자 목적
    frst_acqs_amount: Optional[str] = None  # 최초 취득 금액
    trmend_blce_qy: Optional[str] = None  # 기말 잔액 수량
    trmend_blce_qota_rt: Optional[str] = None  # 기말 잔액 지분율
    trmend_blce_acntbk_amount: Optional[str] = None  # 기말 잔액 장부가액
