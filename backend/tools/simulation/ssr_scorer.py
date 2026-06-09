"""SSR Scorer 툴 — LLM 없이 text-embedding-3-small로 구매의향 점수화."""

from langchain_core.tools import tool
from openai import AsyncOpenAI

client = AsyncOpenAI()

# 구매의향 앵커 텍스트 (KOBACO 데이터 기반으로 교체 가능)
INTENT_ANCHORS = {
    "high": "이 제품을 꼭 사고 싶다. 바로 구매할 의향이 있다.",
    "medium": "관심은 있지만 더 고민해봐야 한다.",
    "low": "별로 관심 없다. 구매할 생각이 없다.",
}


@tool
async def score_purchase_intent(deliberation_text: str) -> float:
    """숙고 텍스트를 임베딩 유사도로 구매의향 점수(0.0~1.0)로 변환합니다.

    LLM 호출 없이 text-embedding-3-small만 사용하여 비용을 절감합니다.

    Args:
        deliberation_text: Deliberation Agent 결과 텍스트

    Returns:
        구매의향 점수 (0.0 = 구매 의향 없음, 1.0 = 강한 구매 의향)
    """
    # TODO: deliberation_text + INTENT_ANCHORS 임베딩 → 코사인 유사도 → 정규화
    raise NotImplementedError
