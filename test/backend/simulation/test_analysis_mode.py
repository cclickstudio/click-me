# 3-모드 분석(A-1) 단위 테스트 — individual 표본 강제 + persona_set 대조 오케스트레이션(LLM 없음)
from __future__ import annotations

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    Persona,
    PersonaReaction,
    SegmentSpec,
    SimulationAggregate,
    SimulationRunRequest,
)
from domain.simulation.service.simulation_service import SimulationService


class _FakeGraph:
    """outer 그래프 스텁 — LLM 없이 interpret→panel→react→aggregate 노드 업데이트를 순서대로 방출.

    load_panel은 sample_size 만큼 페르소나를 만들어 세그먼트별 표본 크기가 결과에 반영되는지 확인 가능.
    """

    async def astream(self, state, *, config=None, stream_mode=None):
        req = state["request"]
        ad = AdInterpretation(ad_id=req.ad_id)
        yield {"interpret_ad": {"ad": ad, "rubric_scores": []}}
        personas = [
            Persona(
                persona_id=f"P-{i}", age=30, gender="F", region="서울", ocean={"openness": 0.5}
            )
            for i in range(req.sample_size)
        ]
        yield {"load_panel": {"personas": personas, "panel_version": "panel-test"}}
        reactions = [
            PersonaReaction(
                persona_id=p.persona_id, aisas=Aisas(action=True), purchase_intent=3, trust=3
            )
            for p in personas
        ]
        yield {"react": {"reactions": reactions}}
        agg = SimulationAggregate(
            click_intent_rate=0.5,
            ci_low=0.4,
            ci_high=0.6,
            purchase_intent=3.0,
            trust_avg=3.0,
            rejection_rate=0.1,
        )
        yield {"aggregate": {"aggregate": agg}}


def _service() -> SimulationService:
    return SimulationService(graph=_FakeGraph(), store=InMemorySimulationStore(), persistence=None)


async def _drain(service: SimulationService, run_id: str) -> str:
    return "".join([chunk async for chunk in service.stream_events(run_id)])


# ── individual: 표본 1 강제 ─────────────────────────────────────────────────


def test_individual_forces_sample_size_one() -> None:
    req = SimulationRunRequest(ad_id="AD-I", analysis_mode="individual", sample_size=50)
    assert req.sample_size == 1
    assert req.allocation == "proportional"  # 1 < 300 → proportional


def test_synthetic_default_unchanged() -> None:
    # 기본은 synthetic이며 표본·배분 해석이 기존과 동일(회귀 0).
    req = SimulationRunRequest(ad_id="AD-S", sample_size=50)
    assert req.analysis_mode == "synthetic"
    assert req.sample_size == 50
    assert req.allocation == "proportional"

    big = SimulationRunRequest(ad_id="AD-B", sample_size=400)
    assert big.allocation == "stratified"


# ── synthetic 회귀: 세그먼트 메타가 섞이지 않는다 ──────────────────────────────


async def test_synthetic_run_has_no_segment_meta() -> None:
    service = _service()
    run_id = await service.start(SimulationRunRequest(ad_id="AD-1", sample_size=4))
    events = await _drain(service, run_id)
    assert '"segment_label"' not in events
    assert '"event": "completed"' in events
    result = service.get_result(run_id)
    assert result["run_id"] == run_id
    assert "mode" not in result  # 단일 런 결과 형태 무변경
    assert len(result["reactions"]) == 4


# ── persona_set: 세그먼트별 개별 실행 대조 ─────────────────────────────────────


async def test_persona_set_shape_and_segment_events() -> None:
    service = _service()
    base = SimulationRunRequest(ad_id="AD-C", analysis_mode="persona_set")
    segments = [
        SegmentSpec(label="20대", target_filter={"age_min": 20, "age_max": 29}, sample_size=3),
        SegmentSpec(label="40대", target_filter={"age_min": 40, "age_max": 49}, sample_size=2),
    ]
    run_id = await service.start_comparison(base, segments)
    events = await _drain(service, run_id)
    result = service.get_result(run_id)

    # 결과 형태 계약: {mode, run_id, segments:[{label, target_filter, sample_size, result}]}
    assert result["mode"] == "persona_set"
    assert result["run_id"] == run_id
    assert [s["label"] for s in result["segments"]] == ["20대", "40대"]
    assert result["segments"][0]["sample_size"] == 3
    assert result["segments"][0]["target_filter"] == {"age_min": 20, "age_max": 29}

    # 세그먼트별 표본 크기가 개별 실행에 반영(3명·2명)되고, 각 세그먼트는 고유 persist run_id.
    seg0, seg1 = result["segments"]
    assert len(seg0["result"]["reactions"]) == 3
    assert len(seg1["result"]["reactions"]) == 2
    assert seg0["result"]["run_id"] != run_id
    assert seg0["result"]["run_id"] != seg1["result"]["run_id"]

    # SSE 진행률에 세그먼트 메타(label·index·total)가 실린다.
    assert '"segment_label": "20\\ub300"' in events or '"segment_label": "20대"' in events
    assert '"segment_index": 0' in events
    assert '"segment_index": 1' in events
    assert '"segment_total": 2' in events
    assert '"event": "completed"' in events
