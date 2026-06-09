"""Persona Factory 툴 — OCEAN Big Five 4계층 페르소나 생성 (GPT-4o-mini T=0.7)."""

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)


@tool
async def generate_personas(count: int = 20) -> list[dict]:
    """OCEAN 4계층 기반 가상 소비자 페르소나를 생성합니다.

    극단 조합 강제로 페르소나 동질화를 방지합니다.

    Args:
        count: 생성할 페르소나 수 (기본 20, 최대 1000)

    Returns:
        OCEAN 프로파일 + 인구통계 + 심리통계를 포함한 페르소나 배열
    """
    # TODO: OCEAN 극단값 샘플링 → LLM 프롬프트 → 페르소나 생성
    raise NotImplementedError
