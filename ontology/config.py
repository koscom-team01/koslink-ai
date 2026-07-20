from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class OntologySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4jpassword"

    DART_API_KEY: str = ""
    DART_CACHE_DIR: str = ".cache/dart"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-haiku-4-5"


@lru_cache
def get_settings() -> OntologySettings:
    return OntologySettings()
