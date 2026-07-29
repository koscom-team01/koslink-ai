"""kosLINK AI - 뉴스 분석 LLM 체인 (추출 → 온톨로지/RAG → 종합, 2단계 호출).

LLM 호출이 2번으로 나뉘는 이유: 온톨로지 조회(연관기업 후보)와 RAG 검색(근거)이
뉴스에서 뽑은 origin_stocks의 ticker를 입력으로 받아야 해서, 그 사이에 끼워
넣을 수밖에 없다.

    [1] extract_key_companies(news, companies)    -> news_summary, origin_stocks
    [2] (retrieval_service) 온톨로지 조회          -> derived_candidates, graph
        ontology_client.find_related_companies(ticker)가 2-hop 이내 OntologyExploreResult
        (related_stocks + graph)를 반환한다 - graph는 retrieval_service가 그대로
        패싱하고, related_stocks만 이 모듈의 DerivedCompanyCandidate로 옮겨 담는다.
    [3] (retrieval_service) RAG 벡터검색           -> vector_context
    [4] synthesize_related_stocks(...)             -> related_stocks, final_summary

related_stocks의 ticker/name/relation_label/relation_path는 LLM에게 시키지
않는다 - 온톨로지 하드 팩트를 그대로 써야 신뢰할 수 있어서, LLM은 그 위에
status(up/down)와 propagation(파급 경로 서술)만 채운다.

final_summary는 종합 호출에서 같이 만든다 - origin_stocks만 있고 연관기업
후보가 하나도 없어도 응답엔 항상 final_summary가 필요해서, [4]는 후보가
비어 있어도 스킵하지 않고 항상 호출한다 (과거엔 후보가 없으면 호출 자체를
생략했지만, 지금은 그러면 final_summary를 만들 수 없다).
"""

from typing import Literal

from pydantic import BaseModel

from app.core.llm.openai_client import get_llm
from app.repositories.company_repository import CompanyRecord
from app.repositories.news_repository import NewsRecord
from app.schemas.news_analysis import Direction, OriginStock


class ExtractionResult(BaseModel):
    news_summary: list[str]
    origin_stocks: list[OriginStock] = []


class DerivedCompanyCandidate(BaseModel):
    """온톨로지 그래프 순회(ontology_client.find_related_companies)로 찾은
    연관기업 후보 (하드팩트). ticker/name/relation_label/relation_path는
    온톨로지가 그대로 채워주는 값 - LLM은 이 위에 status/propagation만 얹는다."""

    ticker: str
    name: str
    relation_label: str
    relation_path: str


class LLMRelatedStock(BaseModel):
    ticker: str
    name: str
    status: Direction
    propagation: str
    evidence_source: Literal["rag", "inferred"]


class _SynthesisResult(BaseModel):
    related_stocks: list[LLMRelatedStock] = []
    final_summary: str


EXTRACTION_SYSTEM_PROMPT = (
    "당신은 금융 뉴스 분석가입니다. 주어진 뉴스를 한국어로 정확히 3문장 요약해 "
    "news_summary 배열(문자열 3개)에 담으세요. 그리고 아래 [기업 유니버스] 안에 "
    "있는 기업 중에서, 이 뉴스가 실제로 주로 다루고 있는 핵심 기업을 "
    "origin_stocks에 딱 1개만 추출하세요 - 여러 기업이 언급되어도 뉴스의 실제 "
    "주인공에 해당하는 가장 핵심적인 기업 하나만 고르고, 유니버스 밖의 기업은 "
    "추출하지 마세요. 그 기업이 이 뉴스로 주가가 오를지(up) 내릴지(down) status를 "
    "판단하고, 왜 이 기업이 뉴스의 메인 기업인지 reason에 근거를 쓰세요."
)

SYNTHESIS_SYSTEM_PROMPT = (
    "당신은 반도체 산업 전문 애널리스트입니다. 뉴스, 온톨로지가 찾은 연관기업 "
    "후보(relation_label/relation_path로 표현된 공급망 관계), 후보마다 딸린 "
    "과거 근거 자료를 받습니다. 후보 목록에 있는 기업에 대해서만 이 뉴스로 주가가 "
    "오를지(up)/내릴지(down) status를 판단하고, 뉴스가 그 기업으로 어떻게 "
    "파급되는지 propagation에 한 문장으로 쓰세요 - 기업명은 *기업명*처럼 별표로 "
    "감싸 강조하세요. 후보 목록에 없는 기업을 새로 만들어내지 마세요 - [주요 기업]에 "
    "나온 origin 기업 자신도 후보 목록에 없다면 related_stocks에 절대 포함하지 "
    "마세요(그 기업은 이미 origin_stocks로 별도 처리됩니다). "
    "반대로 후보 목록에 있는 기업은 하나도 빠짐없이 전부 related_stocks에 "
    "포함해야 합니다 - 근거가 부족하거나 판단이 애매하다는 이유로 후보를 "
    "임의로 누락시키지 마세요. 그 관계 유형(relation_label)이 이번 뉴스의 "
    "소재와 언뜻 안 맞아 보이거나 무관해 보이더라도 마찬가지입니다 - 그 "
    "관계는 온톨로지가 이미 사실로 확인한 하드 팩트이므로, \"관련 없어 "
    "보인다\"는 이유만으로 후보를 통째로 빼는 것도 금지됩니다. 그런 "
    "경우에도 반드시 항목을 작성하고, status/propagation은 관계 유형에 "
    "비추어 논리적으로 타당한 영향을 추론해서 채우세요. 근거가 부족한 "
    "경우의 처리 방법은 아래에 별도로 안내합니다.\n\n"
    "ticker 필드에는 반드시 후보 목록에 표기된 숫자 종목코드만 그대로 넣으세요 "
    "- 회사명을 넣지 마세요. 예를 들어 후보가 \"텔레칩스(054450)\"로 주어졌다면 "
    "ticker=\"054450\", name=\"텔레칩스\"로 쓰고, ticker=\"텔레칩스\"처럼 이름을 "
    "ticker 자리에 넣으면 절대 안 됩니다.\n\n"
    "propagation을 쓸 때 그 기업에 딸린 근거 자료를 아래 기준으로 다루세요:\n"
    "- 근거가 있으면: 그 내용이 실제로 이 기업-관계에 들어맞는지 먼저 검증한 뒤 "
    "반영하고, evidence_source를 'rag'로 표시하세요. 관계와 무관하거나 논리가 "
    "안 맞는 근거는 무시하세요(이 경우 근거가 없는 것과 동일하게 취급).\n"
    "- 근거가 부족하거나 없으면(또는 있어도 무관해서 버렸으면): "
    "relation_label/relation_path와 반도체 산업 일반 지식을 바탕으로 논리적으로 "
    "타당한 파급 경로를 추론해서 문장을 완성하고, evidence_source를 'inferred'로 "
    "표시하세요. 다만 존재를 확인할 수 없는 구체적 수치·날짜·계약명·금액을 "
    "지어내지 마세요 - '~할 가능성이 있다'처럼 추론임을 알 수 있는 어조는 "
    "괜찮습니다.\n"
    "evidence_source는 실제 답변 품질 검증에 쓰이니 정직하게 표시하세요 - 근거를 "
    "참고했다고 매번 'rag'로 표시하지 말고, 조금이라도 자체 추론이 섞였으면 "
    "'inferred'로 표시하세요.\n\n"
    "마지막으로 origin_stocks와 related_stocks 분석 전체를 종합한 3문장 내외의 "
    "final_summary를 작성하세요.\n\n"
    "propagation과 final_summary는 근거 자료(영문 기사 등)가 영어로 되어 있어도 "
    "반드시 한국어로만 작성하세요 - 영어 문장을 그대로 옮기거나 섞어 쓰지 말고 "
    "내용을 한국어로 번역/요약해서 쓰세요."
)


def _build_universe_text(companies: list[CompanyRecord]) -> str:
    return "\n".join(f"- {c.ticker} {c.name}" for c in companies)


def group_evidence_by_ticker(vector_context: list[dict]) -> dict[str, list[dict]]:
    """벡터검색 결과를 후보 기업(ticker) 단위로 묶는다.

    retrieval_service._collect_evidence가 반환하는 vector_context는 후보
    기업들의 근거가 한 리스트에 섞여 있어서(각 항목엔 ticker 필드만 붙어있음),
    프롬프트에 넣을 때(_build_synthesis_prompt)와 evidence_debug를 조립할 때
    (retrieval_service._analyze) 둘 다 "이 근거가 어느 기업 것인지" 구분해야
    해서 공통으로 쓴다."""
    grouped: dict[str, list[dict]] = {}
    for item in vector_context:
        grouped.setdefault(item["ticker"], []).append(item)
    return grouped


async def extract_key_companies(news: NewsRecord, companies: list[CompanyRecord]) -> ExtractionResult:
    llm = get_llm().with_structured_output(ExtractionResult)
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"[기업 유니버스]\n{_build_universe_text(companies)}\n\n"
                f"[뉴스 제목]\n{news.title}\n\n[뉴스 본문]\n{news.body}"
            ),
        },
    ]

    try:
        result = await llm.ainvoke(messages)
    except Exception:
        result = await llm.ainvoke(messages)

    # 프롬프트로 1개만 요청해도 LLM이 어길 수 있어 방어적으로 한 번 더 자른다.
    if len(result.origin_stocks) > 1:
        result = result.model_copy(update={"origin_stocks": result.origin_stocks[:1]})
    return result


def _build_synthesis_prompt(
    news: NewsRecord,
    origin_stocks: list[OriginStock],
    derived_candidates: list[DerivedCompanyCandidate],
    vector_context: list[dict],
) -> str:
    evidence_by_ticker = group_evidence_by_ticker(vector_context)

    if derived_candidates:
        candidate_blocks = []
        for c in derived_candidates:
            evidence_items = evidence_by_ticker.get(c.ticker, [])
            evidence_text = (
                "\n".join(
                    f"    - ({e['source_type']}) {e['title']} ({e['published_date']}): {e.get('text', '')}"
                    for e in evidence_items
                )
                if evidence_items
                else "    근거 자료 없음."
            )
            candidate_blocks.append(f"- {c.name}({c.ticker}): {c.relation_path} [{c.relation_label}]\n  근거:\n{evidence_text}")
        candidates_text = "\n".join(candidate_blocks)
    else:
        candidates_text = "후보 없음."

    return (
        f"[뉴스 제목]\n{news.title}\n\n"
        f"[뉴스 본문]\n{news.body}\n\n"
        f"[주요 기업]\n{[c.name for c in origin_stocks]}\n\n"
        f"[연관기업 후보 및 과거 근거 (온톨로지 + RAG)]\n{candidates_text}"
    )


async def synthesize_related_stocks(
    news: NewsRecord,
    origin_stocks: list[OriginStock],
    derived_candidates: list[DerivedCompanyCandidate],
    vector_context: list[dict],
) -> _SynthesisResult:
    llm = get_llm().with_structured_output(_SynthesisResult)
    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {"role": "user", "content": _build_synthesis_prompt(news, origin_stocks, derived_candidates, vector_context)},
    ]

    try:
        return await llm.ainvoke(messages)
    except Exception:
        return await llm.ainvoke(messages)
