"""kosLINK AI - 뉴스 분석 LLM 체인 (추출 → 온톨로지/RAG → 종합, 2단계 호출).

LLM 호출이 2번으로 나뉘는 이유: 온톨로지 조회(파생기업 후보)와 RAG 검색(근거)이
뉴스에서 뽑은 key_companies의 ticker를 입력으로 받아야 해서, 그 사이에 끼워
넣을 수밖에 없다.

    [1] extract_key_companies(news)              -> news_summary, key_companies
    [2] (retrieval_service) 온톨로지 조회          -> derived_candidates (지금은 항상 [])
    [3] (retrieval_service) RAG 벡터검색           -> vector_context (지금은 mock 고정값)
    [4] synthesize_derived_companies(...)         -> derived_companies

evidence_sources는 LLM에게 시키지 않는다 - url 등 출처 메타데이터를 모델이
지어낼 위험이 있어서, 실제 vector_context에서 그대로 가져와 붙이는 건
retrieval_service의 몫이다 (docs/rag_architecture.md 7장 "[6] 응답 조립" 참고).

derived_candidates(온톨로지 후보)가 비어있으면 종합 호출 자체를 생략한다 -
근거 없이 LLM을 불러봤자 항상 빈 배열만 나오는 게 뻔해서 API 호출을 아낀다.
"""

from typing import Literal

from pydantic import BaseModel

from app.core.llm.openai_client import get_llm
from app.repositories.news_repository import NewsRecord
from app.schemas.news_analysis import KeyCompany


class ExtractionResult(BaseModel):
    news_summary: str
    key_companies: list[KeyCompany] = []


class DerivedCompanyCandidate(BaseModel):
    """온톨로지 그래프 순회로 찾은 파생기업 후보 (하드팩트). 아직 ontology_client가
    없어서 지금은 항상 빈 리스트로 들어온다."""

    ticker: str
    name: str
    derived_from: str
    supply_relation: str


class LLMDerivedCompany(BaseModel):
    ticker: str
    name: str
    derived_from: str
    supply_relation: str
    market_sentiment: Literal["긍정적", "중립적", "부정적"]
    prediction: Literal["상승세", "보합", "하락세"]
    rationale: str


class _SynthesisResult(BaseModel):
    derived_companies: list[LLMDerivedCompany] = []


EXTRACTION_SYSTEM_PROMPT = (
    "당신은 금융 뉴스 분석가입니다. 주어진 뉴스를 한국어로 2~3문장으로 요약하고, "
    "단순히 이름이 언급된 기업이 아니라 이 뉴스가 실제로 주로 다루고 있는 핵심 "
    "기업을 추출하세요(ticker는 아는 경우에만 정확히 채우고 모르면 빈 문자열로 "
    "둡니다)."
)

SYNTHESIS_SYSTEM_PROMPT = (
    "당신은 반도체 산업 전문 애널리스트입니다. 뉴스, 온톨로지가 찾은 파생기업 후보"
    "(공급망 관계), 그 기업들에 대한 과거 근거 자료를 받습니다. 후보 목록에 있는 "
    "기업에 대해서만 시장 반응(market_sentiment)과 전망(prediction), 판단 근거"
    "(rationale)를 작성하세요. 후보 목록에 없는 기업을 새로 만들어내지 마세요."
)


async def extract_key_companies(news: NewsRecord) -> ExtractionResult:
    llm = get_llm().with_structured_output(ExtractionResult)
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": f"[뉴스 제목]\n{news.title}\n\n[뉴스 본문]\n{news.body}"},
    ]

    try:
        return await llm.ainvoke(messages)
    except Exception:
        return await llm.ainvoke(messages)


def _build_synthesis_prompt(
    news: NewsRecord,
    key_companies: list[KeyCompany],
    derived_candidates: list[DerivedCompanyCandidate],
    vector_context: list[dict],
) -> str:
    candidates_text = "\n".join(
        f"- {c.name}({c.ticker}): {c.derived_from} 기준 {c.supply_relation}" for c in derived_candidates
    )
    if vector_context:
        evidence_text = "\n".join(
            f"- ({c['source_type']}) {c['title']} ({c['published_date']}): {c.get('text', '')}"
            for c in vector_context
        )
    else:
        evidence_text = "근거 자료 없음."

    return (
        f"[뉴스 제목]\n{news.title}\n\n"
        f"[뉴스 본문]\n{news.body}\n\n"
        f"[주요 기업]\n{[c.name for c in key_companies]}\n\n"
        f"[파생기업 후보 (온톨로지)]\n{candidates_text}\n\n"
        f"[과거 이벤트 (RAG 검색)]\n{evidence_text}"
    )


async def synthesize_derived_companies(
    news: NewsRecord,
    key_companies: list[KeyCompany],
    derived_candidates: list[DerivedCompanyCandidate],
    vector_context: list[dict],
) -> list[LLMDerivedCompany]:
    if not derived_candidates:
        return []

    llm = get_llm().with_structured_output(_SynthesisResult)
    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": _build_synthesis_prompt(news, key_companies, derived_candidates, vector_context)},
    ]

    try:
        result = await llm.ainvoke(messages)
    except Exception:
        result = await llm.ainvoke(messages)
    return result.derived_companies
