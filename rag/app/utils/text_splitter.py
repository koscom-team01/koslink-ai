"""kosLINK AI - 청킹 + 프리픽스 조립.

scripts/backfill_corpus.py(사전 백필)와 향후 실시간 사후 임베딩이 공통으로 쓰는
단일 구현. langflow/components/koslink/chunk_and_prefix.py(Langflow 데모 플로우)는
별도 컨테이너에서 이 app 패키지를 import할 수 없어 동일 로직을 독립적으로 유지한다.
"""

from langchain_text_splitters import RecursiveCharacterTextSplitter

# NVIDIA FinanceBench 연구(금융 문서 대상) 기준 1024토큰 + 15% 오버랩이 최적으로
# 확인됨. 이 코퍼스는 한국어라 실측 토큰/글자 비율(cl100k_base 기준 글자당 약
# 1.0토큰)을 적용해 토큰 단위를 글자 단위로 그대로 대응시켰다.
CHUNK_SIZE = 1024
CHUNK_OVERLAP = 150


def get_splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)


def build_prefix(*parts: str) -> str:
    """청크 앞에 붙는 문맥 프리픽스.

    발행일/URL처럼 자연어 문장이 아닌 날것의 태그는 넣지 않는다 - 임베딩 품질에
    노이즈로 작용하기 때문(rag_db_schema.md 2-0절). 그런 값은 metadata로만 저장한다.
    """
    joined = " ".join(p for p in parts if p)
    return f"[{joined}]\n"
