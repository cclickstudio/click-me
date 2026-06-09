"""Ad Creator Agent — LangGraph 노드 함수 (7.8 목표)."""

from agents.agent_ad_creator.state import AdCreatorState


async def select_debate_personas(state: AdCreatorState) -> AdCreatorState:
    """Persona Pool에서 다양성 보장 페르소나 5명 선발."""
    # TODO: tools.persona.factory에서 극단 OCEAN 조합 5명 선발
    return state


async def run_debate(state: AdCreatorState) -> AdCreatorState:
    """페르소나 간 다중 라운드 토론 — Debate Agent (Claude Haiku T=0.9)."""
    # TODO: 각 페르소나가 광고 방향성에 대해 주장·반박 (3 라운드)
    return state


async def vote(state: AdCreatorState) -> AdCreatorState:
    """토론 후 투표 — 채택 광고 방향성 결정."""
    # TODO: 다수결 투표 + 근거 요약
    return state


async def generate_ad(state: AdCreatorState) -> AdCreatorState:
    """광고 생성 — 텍스트(Gemini Flash) / 이미지(GPT Image 2) / 영상(Gemini Omni)."""
    # TODO: ad_type 분기 → 각 생성 툴 호출 → S3 저장
    return state
