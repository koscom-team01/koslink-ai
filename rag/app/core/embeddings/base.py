"""kosLINK AI - 임베딩 프로바이더 계약.

LangChain의 Embeddings 추상클래스(embed_documents/embed_query)를 그대로 계약으로
쓴다(docs/rag_architecture.md 3장). 별도 인터페이스를 새로 정의하지 않고,
factory.py가 이 타입을 반환하는 함수로 openai/kure 구현체를 스위칭한다.
"""

from langchain_core.embeddings import Embeddings as EmbeddingProvider

__all__ = ["EmbeddingProvider"]
