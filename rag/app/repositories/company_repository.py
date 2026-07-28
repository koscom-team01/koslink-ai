"""kosLINK AI - companies 테이블(대상 51개 기업 유니버스) 조회 리포지토리.

companies도 news와 마찬가지로 app/db/base.py의 Declarative Base로 매핑하지
않고 SQLAlchemy Core로 직접 조회한다. origin_stocks 추출 시 LLM이 이 유니버스
밖의 기업을 지어내지 않도록 프롬프트에 그대로 넣어줄 목적으로만 쓴다.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CompanyRecord:
    ticker: str
    name: str


class CompanyRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def list_all(self) -> list[CompanyRecord]:
        result = await self._session.execute(text("SELECT ticker, name FROM companies ORDER BY ticker"))
        rows = result.mappings().all()
        return [CompanyRecord(**row) for row in rows]
