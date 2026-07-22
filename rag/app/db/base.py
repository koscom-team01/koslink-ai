"""kosLINK AI - RAG 서버 소유 SQLAlchemy 모델 공통 Base.

companies/disclosures/news 등 rag/sql/*.sql로 이미 생성된 테이블은 여기 매핑하지
않는다 - RAG가 직접 소유하는 보조 테이블(예: 청크 메타데이터)이 생기면 이 Base를
상속해서 정의한다.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
