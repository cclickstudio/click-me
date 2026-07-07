# outer 그래프 반응 fan-out 견고성 테스트 — 1명 실패는 건너뛰고 진행 / 전원 실패는 RuntimeError
from __future__ import annotations

import pytest

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    Persona,
    PersonaReaction,
    SimulationRunRequest,
)
from domain.simulation.graph.reaction_graph import build_reaction_graph
from domain.simulation.graph.run_graph import build_run_graph
from domain.simulation.service.simulation_service import SimulationService
from domain.simulation.tools.aggregation.aggregator import BasicAggregator


def _persona(pid: str) -> Persona:
    return Persona(persona_id=pid, age=30, gender="F", region="서울", ocean={"openness": 0.5})


class _Interpreter:
    async def interpret(self, request: SimulationRunRequest) -> AdInterpretation:
        return AdInterpretation(ad_id=request.ad_id)


class _Rubric:
    async def evaluate(self, ad, request):  # 선언 입력 없음 → 정합 차원 없음
        return []


class _Panel:
    def __init__(self, personas: list[Persona]) -> None:
        self._personas = personas

    async def get_or_build(self, spec):
        return "panel-test", self._personas


class _Reactor:
    """지정 persona_id 는 반응 생성에서 예외 → fan-out 실패 경로 유발."""

    def __init__(self, fail_ids: set[str]) -> None:
        self._fail_ids = fail_ids

    async def react(self, persona: Persona, ad: AdInterpretation) -> PersonaReaction:
        if persona.persona_id in self._fail_ids:
            raise RuntimeError("reactor boom")
        return PersonaReaction(
            persona_id=persona.persona_id, aisas=Aisas(action=True), purchase_intent=3, trust=3
        )


class _Qa:
    async def check(self, reaction, attempt, *, persona=None, ad=None):
        return True, None


def _service(personas: list[Persona], fail_ids: set[str]) -> SimulationService:
    reaction_graph = build_reaction_graph(reactor=_Reactor(fail_ids), qa=_Qa())
    graph = build_run_graph(
        interpreter=_Interpreter(),
        panel=_Panel(personas),
        rubric=_Rubric(),
        aggregator=BasicAggregator(),
        reaction_graph=reaction_graph,
    )
    return SimulationService(graph=graph, store=InMemorySimulationStore())


async def test_single_persona_failure_is_skipped_rest_aggregated() -> None:
    # 3명 중 1명 반응 실패 → 나머지 2명만 집계, 런은 정상 완료.
    personas = [_persona(f"P-{i}") for i in range(3)]
    svc = _service(personas, fail_ids={"P-1"})
    result = await svc.run(SimulationRunRequest(ad_id="AD-1", sample_size=3))
    assert result["aggregate"]["payload"]["qa_passed_count"] == 2
    assert len(result["reactions"]) == 2


async def test_all_personas_failure_raises_runtime_error() -> None:
    # 전원 반응 실패 → 무표본 → 서비스가 RuntimeError 로 승격.
    personas = [_persona(f"P-{i}") for i in range(3)]
    svc = _service(personas, fail_ids={"P-0", "P-1", "P-2"})
    with pytest.raises(RuntimeError, match="모든 페르소나"):
        await svc.run(SimulationRunRequest(ad_id="AD-1", sample_size=3))
