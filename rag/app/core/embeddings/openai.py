"""kosLINK AI - OpenAI 임베딩 구현체 (해커톤 주최측 제공 키 사용, 기본 프로바이더)."""

from langchain_openai import OpenAIEmbeddings

from app.config import get_settings


def build_openai_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.OPENAI_EMBEDDING_MODEL,
        api_key=settings.OPENAI_API_KEY,
    )
