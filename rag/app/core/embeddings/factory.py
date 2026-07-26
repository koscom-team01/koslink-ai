"""kosLINK AI - EMBEDDING_PROVIDER 환경변수로 임베딩 구현체를 선택 (docs/rag_architecture.md 3장)."""

from functools import lru_cache

from app.config import get_settings
from app.core.embeddings.base import EmbeddingProvider
from app.core.embeddings.kure import KureEmbeddings
from app.core.embeddings.openai import build_openai_embeddings


@lru_cache
def get_embedding_provider() -> EmbeddingProvider:
    provider = get_settings().EMBEDDING_PROVIDER
    if provider == "openai":
        return build_openai_embeddings()
    if provider == "kure":
        return KureEmbeddings()
    raise ValueError(f"지원하지 않는 EMBEDDING_PROVIDER: {provider}")
