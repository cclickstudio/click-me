"""Exposure Agent 툴 — 페르소나의 광고 즉각 반응 생성 (GPT-4o-mini T=0.8)."""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8)


@tool
async def run_exposure(persona: dict, ad_content: dict) -> str:
    """광고에 노출된 페르소나의 즉각적인 감정·인지 반응을 생성합니다.

    Args:
        persona: OCEAN 프로파일 + 인구통계
        ad_content: Ad Understanding Agent 분석 결과

    Returns:
        즉각 반응 텍스트 (감정, 연상 이미지, 초기 판단)
    """
    # TODO: 페르소나 특성 반영 프롬프트 → GPT-4o-mini 호출
    raise NotImplementedError
