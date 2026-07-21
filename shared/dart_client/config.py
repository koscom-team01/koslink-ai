from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DartSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DART_API_KEY: str = ""
    DART_CACHE_DIR: str = ".cache/dart"


@lru_cache
def get_dart_settings() -> DartSettings:
    return DartSettings()
