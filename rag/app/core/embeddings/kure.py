"""kosLINK AI - KURE-v1 임베딩 구현체 (embedding_server/ 로컬 Infinity 서버 폴백 경로).

langchain_openai.OpenAIEmbeddings는 tiktoken으로 텍스트를 토큰ID 배열로 미리
인코딩해서 보내는데, Infinity 서버(OpenAI 호환 /embeddings API)는 원문 문자열을
기대하는 구조라 호환이 안 된다(Langflow 커스텀 컴포넌트에서 겪은 것과 동일한
문제) - 그래서 직접 HTTP 호출로 우회한다.
"""

import requests
from langchain_core.embeddings import Embeddings

from app.config import get_settings

_EMBED_REQUEST_BATCH_SIZE = 3
_REQUEST_TIMEOUT_SEC = 1800


class KureEmbeddings(Embeddings):
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.EMBEDDING_SERVER_URL
        self._model = settings.EMBEDDING_MODEL_KURE

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for i in range(0, len(texts), _EMBED_REQUEST_BATCH_SIZE):
            batch = texts[i : i + _EMBED_REQUEST_BATCH_SIZE]
            resp = requests.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": batch},
                timeout=_REQUEST_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            embeddings.extend(item["embedding"] for item in resp.json()["data"])
        return embeddings

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
