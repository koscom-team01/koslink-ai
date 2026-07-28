"""kosLINK AI - 청킹 + 임베딩 + pgvector 적재 오케스트레이션 (docs/rag_architecture.md 2장/7장).

scripts/backfill_corpus.py(사전 백필)와 retrieval_service.py의
_trigger_post_response_embedding(실시간 뉴스 사후 임베딩)이 공통으로 쓰는 단일 구현.
"""

from langchain_core.documents import Document
from langchain_postgres import PGVector

from app.config import get_settings
from app.core.embeddings.factory import get_embedding_provider
from app.utils.text_splitter import get_splitter


def build_async_vector_store() -> PGVector:
    """retrieval_service.py(FastAPI 요청 처리 중 호출)용 비동기 PGVector 인스턴스."""
    settings = get_settings()
    return PGVector(
        embeddings=get_embedding_provider(),
        collection_name=settings.VECTOR_COLLECTION_NAME,
        connection=settings.PG_CONNECTION_STRING,
        async_mode=True,
    )


def _build_chunk_documents(docs_input: list[tuple[str, str, dict]]) -> list[Document]:
    splitter = get_splitter()
    all_docs: list[Document] = []
    for prefix, content, metadata in docs_input:
        raw_chunks = splitter.split_text(content or "")
        for idx, chunk in enumerate(raw_chunks):
            all_docs.append(
                Document(
                    page_content=prefix + chunk,
                    metadata={**metadata, "chunk_index": idx},
                )
            )
    return all_docs


def chunk_and_store(docs_input: list[tuple[str, str, dict]], vector_store: PGVector) -> int:
    """(프리픽스, 본문, metadata) 쌍 리스트를 청킹해서 벡터DB에 저장하고 청크 수를 반환.

    scripts/backfill_corpus.py(동기 스크립트)가 쓰는 동기 버전.
    """
    all_docs = _build_chunk_documents(docs_input)
    if all_docs:
        vector_store.add_documents(all_docs)
    return len(all_docs)


async def achunk_and_store(docs_input: list[tuple[str, str, dict]], vector_store: PGVector) -> int:
    """chunk_and_store의 비동기 버전. retrieval_service.py(FastAPI 요청 처리 중 호출)가 쓴다."""
    all_docs = _build_chunk_documents(docs_input)
    if all_docs:
        await vector_store.aadd_documents(all_docs)
    return len(all_docs)
