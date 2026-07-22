"""
kosLINK AI - RAG 서버 공통 설정
모든 값은 환경변수로 주입받는다. 로컬(Windows/Mac)은 connect_db.sh 터널을 통한
localhost 접속을, 배포 환경은 별도 주입값을 그대로 사용하므로 이 파일은 수정하지 않는다.
"""

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # PostgreSQL (RDBMS + pgvector 공용)
    PG_CONNECTION_STRING: str = "postgresql+psycopg://admin:adminpassword@localhost:5432/koscomdb"

    # Neo4j (온톨로지 조회)
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4jpassword"

    # OpenAI API
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # 임베딩: kure | bge_m3
    EMBEDDING_PROVIDER: str = "kure"
    EMBEDDING_MODEL_KURE: str = "nlpai-lab/KURE-v1"
    EMBEDDING_MODEL_BGE_M3: str = "BAAI/bge-m3"
    EMBEDDING_DEVICE: str = "cpu"

    VECTOR_COLLECTION_NAME: str = "market_news"

    PORT: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
