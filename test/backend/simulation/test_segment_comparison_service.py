# Persona Set(3-모드 UX §A-1) 세그먼트 비교 서비스 단위테스트 — 전부 LLM✗(스텁)
from __future__ import annotations

from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    Persona,
    PersonaReaction,
    SegmentSpec,
    SimulationRunRequest,
)
from domain.simulation.graph.reaction_graph import build_reaction_graph
from domain.simulation.service.segment_comparison_service import SegmentComparisonService
from domain.simulation.tools.aggregation.aggregator import BasicAggregator
from domain.simulation.tools.sampling.persona_sampler import PersonaSampler


class _StubInterpreter:
    """광고 해석 호출 횟수만 센다 — 세그먼트 수와 무관하게 1회여야 함(핵심 검증 대상)."""

    def __init__(self) -> None:
        self.calls = 0

    async def interpret(self, request: SimulationRunRequest) -> AdInterpretation:
        self.calls += 1
        return AdInterpretation(ad_id=request.ad_id)


class _StubRubric:
    def __init__(self) -> None:
        self.calls = 0

    async def evaluate(self, ad, request):
        self.calls += 1
        return []


class _StubReactor:
    async def react(self, persona: Persona, ad: AdInterpretation) -> PersonaReaction:
        return PersonaReaction(
            persona_id=persona.persona_id, aisas=Aisas(action=True), purchase_intent=3, trust=3
        )


class _AlwaysPassQa:
    async def check(self, reaction, attempt, *, persona=None, ad=None):
        return True, None


def _service() -> tuple[SegmentComparisonService, _StubInterpreter, _StubRubric]:
    interpreter = _StubInterpreter()
    rubric = _StubRubric()
    service = SegmentComparisonService(
        interpreter=interpreter,
        rubric=rubric,
        panel=PersonaSampler(),
        reaction_graph=build_reaction_graph(reactor=_StubReactor(), qa=_AlwaysPassQa()),
        aggregator=BasicAggregator(),
    )
    return service, interpreter, rubric


async def test_interprets_ad_once_regardless_of_segment_count() -> None:
    service, interpreter, rubric = _service()
    request = SimulationRunRequest(ad_id="AD-SEG")
    segments = [
        SegmentSpec(label="20대 여성", target_filter={"gender": "F", "age_min": 20, "age_max": 29}),
        SegmentSpec(label="40대 남성", target_filter={"gender": "M", "age_min": 40, "age_max": 49}),
        SegmentSpec(label="전체", target_filter=None),
    ]

    result = await service.run(request, segments)

    assert interpreter.calls == 1  # 세그먼트 3개인데도 광고 해석은 1회
    assert rubric.calls == 1
    assert len(result["segments"]) == 3


async def test_segment_personas_respect_target_filter() -> None:
    service, _, _ = _service()
    request = SimulationRunRequest(ad_id="AD-SEG")
    segments = [
        SegmentSpec(
            label="20대 여성",
            target_filter={"gender": "F", "age_min": 20, "age_max": 29},
            sample_size=15,
        ),
    ]

    result = await service.run(request, segments)
    seg = result["segments"][0]

    assert seg["label"] == "20대 여성"
    assert seg["personas"]
    assert all(p.gender == "F" and 20 <= p.age <= 29 for p in seg["personas"])
    assert seg["sample_size"] == len(seg["personas"])
    assert seg["aggregate"] is not None
    assert len(seg["reactions"]) == len(seg["personas"])
