"""
kosLINK AI - RAG 청킹 + 메타데이터 프리픽스 조립 Langflow Custom Component

Langflow의 내장 노드 기능이 아닌 다음 두가지의 역할을 별도로 명시
1. RecursiveCharacterTextSplitter로 본문을 청크 단위로 분할 (큰 청크 기준)
2. 각 청크 앞에 [기업명]/[발행일]/[문서유형] 프리픽스를 붙여, 임베딩 벡터에 엔티티 정보가
   녹아들도록 한다 (본문에 회사명이 대명사로만 언급되는 경우 검색 정확도가 떨어지는 문제 방지).
"""

from lfx.custom.custom_component.component import Component
from lfx.io import DropdownInput, IntInput, MessageTextInput, Output
from lfx.schema import Data

from langchain_text_splitters import RecursiveCharacterTextSplitter


class ChunkAndPrefixComponent(Component):
    display_name = "Chunk & Prefix (kosLINK)"
    description = "뉴스/공시 원문을 청크로 분할하고 [기업명]/[발행일]/[문서유형] 프리픽스를 붙인다."

    inputs = [
        MessageTextInput(name="source_doc_id",
                         display_name="원본 식별자 (news_id / rcept_no)"),
        DropdownInput(
            name="source_type",
            display_name="문서 종류",
            options=["news", "disclosure"],
        ),
        MessageTextInput(name="company", display_name="기업명 (프리픽스 텍스트용)"),
        MessageTextInput(name="ticker", display_name="티커", value=""),
        MessageTextInput(name="published_date",
                         display_name="발행일 (YYYY-MM-DD)"),
        MessageTextInput(name="doc_type", display_name="문서유형 (예: 정기공시, 뉴스)"),
        MessageTextInput(name="title", display_name="제목"),
        MessageTextInput(name="url", display_name="원문 링크", value=""),
        MessageTextInput(name="content", display_name="본문"),
        IntInput(name="chunk_size", display_name="청크 크기(문자)", value=3000),
        IntInput(name="chunk_overlap", display_name="청크 오버랩(문자)", value=200),
    ]

    outputs = [
        Output(name="chunks", display_name="Chunks", method="build_chunks"),
    ]

    def _build_prefix(self) -> str:
        return (
            f"[기업명: {self.company}] [발행일: {self.published_date}] "
            f"[문서유형: {self.doc_type}]\n제목: {self.title}\n본문: "
        )

    def build_chunks(self) -> list[Data]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        raw_chunks = splitter.split_text(self.content or "")
        if not raw_chunks:
            raw_chunks = [""]

        prefix = self._build_prefix()

        records = [
            Data(
                data={
                    "source_type": self.source_type,
                    "source_doc_id": self.source_doc_id,
                    "chunk_index": idx,
                    "ticker": self.ticker,
                    "title": self.title,
                    "url": self.url,
                    "published_date": self.published_date,
                    # 프리픽스는 청크마다 반복해서 붙인다 - 뒤쪽 청크만 떼어놓고 봐도
                    # "어느 회사/어느 문서" 맥락이 임베딩 벡터에 남아있어야 하기 때문.
                    # "text"는 Data.to_lc_document()가 page_content로 인식하는 예약 키.
                    "text": prefix + chunk_text,
                }
            )
            for idx, chunk_text in enumerate(raw_chunks)
        ]

        self.status = f"{len(records)}개 청크 생성"
        return records
