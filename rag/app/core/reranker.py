"""kosLINK AI - 검색 결과 리랭커 (Dongjin-kr/ko-reranker).

BAAI/bge-reranker-large를 한국어로 파인튜닝한 cross-encoder. AWS AIML
스페셜리스트 솔루션즈 아키텍트가 만들어 AWS 공식 한국 기술 블로그에 소개된
모델이라 출처 신뢰도가 있고, KURE 임베딩과 비슷한 체급(5억대 파라미터)이라
무겁지 않다.

셀프호스팅 cross-encoder라 sentence-transformers/torch가 필요하다 - 이미
rag/requirements.txt에서 한 번 제거된 이력이 있는 무거운 의존성이라(Docker
빌드 최적화 커밋 참고), 아직 requirements.txt에는 안 넣고 로컬 .venv에만
설치해서 개발 중이다. 배포 방식(메인 이미지에 포함 vs 별도 서비스 분리)은
배포 담당자와 별도로 결정한다.

모델 카드 권장 사용법을 그대로 따른다: (query, passage) 쌍의 원본 logit을
구하고, 같은 질의의 후보군 전체를 대상으로 exp_normalize(softmax류)로
정규화한 뒤 내림차순 정렬한다.
"""

from functools import lru_cache

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from app.config import get_settings

_MAX_LENGTH = 512


@lru_cache
def _load_model():
    settings = get_settings()
    tokenizer = AutoTokenizer.from_pretrained(settings.RERANKER_MODEL)
    model = AutoModelForSequenceClassification.from_pretrained(settings.RERANKER_MODEL)
    model.eval()
    return tokenizer, model


def _exp_normalize(x: np.ndarray) -> np.ndarray:
    b = x.max()
    y = np.exp(x - b)
    return y / y.sum()


def rerank(query: str, candidates: list[dict], *, text_key: str = "text", top_k: int = 5) -> list[dict]:
    """(query, candidate[text_key]) 쌍을 점수화해서 상위 top_k만 내림차순으로 반환.

    candidates가 비어있으면 모델 로딩 자체를 스킵하고 빈 리스트를 반환한다.
    """
    if not candidates:
        return []

    tokenizer, model = _load_model()
    pairs = [[query, c[text_key]] for c in candidates]

    with torch.no_grad():
        inputs = tokenizer(pairs, padding=True, truncation=True, return_tensors="pt", max_length=_MAX_LENGTH)
        logits = model(**inputs, return_dict=True).logits.view(-1).float().numpy()

    scores = _exp_normalize(logits)
    ranked = sorted(zip(candidates, scores), key=lambda pair: pair[1], reverse=True)
    return [candidate for candidate, _ in ranked[:top_k]]
