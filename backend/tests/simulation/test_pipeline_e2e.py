# 시뮬레이터 파이프라인 end-to-end 스모크 — 실 Gemini로 광고→반응→집계 한 바퀴 검증
#
# mock 제거로 실 LLM 전용 → 비용·비결정성 때문에 RUN_LIVE_LLM=1 일 때만 실행(기본 skip).
# 실데이터 검증: RUN_LIVE_LLM=1 로 이 파일을 pytest 실행.
from __future__ import annotations

import os

import pytest

from domain.simulation.contracts.schemas import SimulationRunRequest
from domain.simulation.wiring import build_simulation_service

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_LIVE_LLM") != "1",
    reason="실 Gemini e2e — RUN_LIVE_LLM=1로 명시 실행(mock 제거)",
)

_AGG_KEYS = (
    "click_intent_rate",
    "ci_low",
    "ci_high",
    "purchase_intent",
    "trust_avg",
    "rejection_rate",
    "variance_warning",
    "effective_n",
    "engine_version",
)


async def _drain(service, run_id: str) -> list[str]:
    return [chunk async for chunk in service.stream_events(run_id)]


async def test_per_persona_progress_emitted() -> None:
    # outer 그래프 astream → 페르소나별 반응 진행률이 SSE로 보존되는지(P6 통합).
    service = build_simulation_service()
    sample = 15
    run_id = await service.start(SimulationRunRequest(ad_id="AD-P", sample_size=sample))
    events = await _drain(service, run_id)

    reaction_msgs = [e for e in events if '"stage": "reaction"' in e and '"message"' in e]
    assert len(reaction_msgs) == sample
    assert f"반응 {sample}/{sample}" in reaction_msgs[-1]


async def test_pipeline_runs_end_to_end() -> None:
    service = build_simulation_service()
    request = SimulationRunRequest(ad_id="AD-TEST", sample_size=30)

    run_id = await service.start(request)
    events = await _drain(service, run_id)

    # SSE가 완료 이벤트로 끝난다(중간 실패 아님).
    assert any('"event": "completed"' in e for e in events)
    assert not any('"event": "error"' in e for e in events)

    result = service.get_result(run_id)
    assert result is not None
    assert result["run_id"] == run_id


async def test_ad_and_simulation_blocks_present() -> None:
    # ERD 광고·시뮬레이션 테이블 데이터가 run 결과에 인메모리로 조립돼 나오는지(ERD 5테이블 출력).
    service = build_simulation_service()
    request = SimulationRunRequest(
        ad_id="AD-BLK", sample_size=20, ad_title="신제품", product_category="음료"
    )
    run_id = await service.start(request)
    await _drain(service, run_id)

    result = service.get_result(run_id)
    assert {"ad", "simulation"}.issubset(result)

    ad = result["ad"]
    assert ad["ID"] == "AD-BLK"
    assert ad["title"] == "신제품"
    assert ad["product_category"] == "음료"

    sim = result["simulation"]
    assert sim["ad_id"] == "AD-BLK"
    assert sim["sample_size"] == 20
    assert sim["status"] == "COMPLETED"
    assert sim["qa_passed_count"] == sum(1 for r in result["reactions"] if r["qa_passed"])


async def test_reaction_contract_fields_present() -> None:
    service = build_simulation_service()
    run_id = await service.start(SimulationRunRequest(ad_id="AD-1", sample_size=20))
    await _drain(service, run_id)

    reactions = service.get_result(run_id)["reactions"]
    assert reactions, "반응이 한 건도 생성되지 않음"

    # §3.5 반응 스키마 계약 필드.
    required = {"persona_id", "aisas", "purchase_intent", "trust", "emotion_tag", "qa_passed"}
    for r in reactions:
        assert required.issubset(r), f"누락 필드: {required - set(r)}"
        assert 1 <= r["purchase_intent"] <= 5
        assert 1 <= r["trust"] <= 5
        assert set(r["aisas"]) == {"attention", "interest", "search", "action", "share"}


async def test_aggregate_contract_and_ranges() -> None:
    service = build_simulation_service()
    run_id = await service.start(SimulationRunRequest(ad_id="AD-2", sample_size=40))
    await _drain(service, run_id)

    agg = service.get_result(run_id)["aggregate"]
    for key in _AGG_KEYS:
        assert key in agg, f"집계 계약 누락: {key}"

    assert 0.0 <= agg["click_intent_rate"] <= 1.0
    assert agg["ci_low"] <= agg["click_intent_rate"] <= agg["ci_high"]
    assert 0.0 <= agg["rejection_rate"] <= 1.0
    assert 1.0 <= agg["purchase_intent"] <= 5.0
    assert agg["engine_version"] == "agg-2"
    # 도달성은 추출분포에 반영(§Tier1)·self-weighting 유지 → 균일 가중 → 유효표본수 = 표본수.
    assert agg["effective_n"] == 40.0
