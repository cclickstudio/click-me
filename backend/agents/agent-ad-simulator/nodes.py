"""Ad Simulator Agent — LangGraph 노드 함수."""

from agents.agent_ad_simulator.state import SimulatorState


async def generate_personas(state: SimulatorState) -> SimulatorState:
    """Persona Factory 툴 호출 → OCEAN 4계층 페르소나 생성 (GPT-4o-mini T=0.7)."""
    # TODO: tools.persona.factory.generate_personas 호출
    return state


async def run_exposure(state: SimulatorState) -> SimulatorState:
    """각 페르소나의 즉각 반응 생성 — 병렬 실행 (GPT-4o-mini T=0.8)."""
    # TODO: tools.simulation.exposure.run 호출 (asyncio.gather로 병렬)
    return state


async def run_deliberation(state: SimulatorState) -> SimulatorState:
    """각 페르소나의 내면 처리 생성 (GPT-4o-mini T=0.7)."""
    # TODO: tools.simulation.deliberation.run 호출
    return state


async def score_with_ssr(state: SimulatorState) -> SimulatorState:
    """SSR Scorer — LLM 없이 text-embedding-3-small로 점수화."""
    # TODO: tools.simulation.ssr_scorer.score 호출
    return state


async def build_distribution(state: SimulatorState) -> SimulatorState:
    """페르소나 응답을 집계하여 구매의향 분포(Distribution) 생성."""
    # TODO: 분포 집계 로직
    return state
