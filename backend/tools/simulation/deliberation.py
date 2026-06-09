"""Deliberation Agent 툴 — 페르소나의 내면 처리 생성 (GPT-4o-mini T=0.7)."""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)


@tool
async def run_deliberation(persona: dict, exposure_reaction: str, ad_content: dict) -> str:
    """즉각 반응 이후 페르소나의 숙고 과정(이성적 판단·구매 검토)을 생성합니다.

    Args:
        persona: OCEAN 프로파일 + 인구통계
        exposure_reaction: Exposure Agent 결과
        ad_content: 광고 분석 데이터

    Returns:
        내면 처리 텍스트 (가격 민감도, 브랜드 태도, 구매 의향 근거)
    """
    # TODO: exposure_reaction 맥락 포함 프롬프트 → GPT-4o-mini 호출
    raise NotImplementedError
