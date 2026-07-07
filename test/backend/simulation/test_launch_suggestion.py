# 시뮬 완료 → 집행 제안(launch_suggest) 훅 — 게이트 통과 시 생성·미달 시 미생성
from types import SimpleNamespace

from domain.simulation.service import simulation_service


def _request():
    return SimpleNamespace(
        project_id="proj-1",
        organization_id="org-1",
        ad_title="테스트 광고",
        user_id="user-1",
    )


def _result(cir: float, rej: float):
    return {
        "simulation_id": "sim-1",
        "aggregate": {"click_intent_rate": cir, "rejection_rate": rej},
    }


async def test_launch_suggest_created_when_gate_passes(monkeypatch):
    calls = []

    async def fake_create(**kw):
        calls.append(kw)

    monkeypatch.setattr(simulation_service, "create_center_suggestion", fake_create)
    await simulation_service._record_launch_suggestion(_request(), _result(0.02, 0.1))
    assert len(calls) == 1
    kw = calls[0]
    assert kw["suggestion_type"] == "launch_suggest"
    assert kw["dedup_key"] == "launch_suggest:sim-1"
    assert kw["payload"]["click_intent_rate"] == 0.02
    assert kw["payload"]["rejection_rate"] == 0.1


async def test_launch_suggest_skipped_below_gate(monkeypatch):
    calls = []

    async def fake_create(**kw):
        calls.append(kw)

    monkeypatch.setattr(simulation_service, "create_center_suggestion", fake_create)
    # 거부율 20% 정확히 = 실패(<) — 경계 검증
    await simulation_service._record_launch_suggestion(_request(), _result(0.02, 0.2))
    # 클릭 1% 미만 = 실패
    await simulation_service._record_launch_suggestion(_request(), _result(0.009, 0.0))
    assert calls == []


async def test_launch_suggest_skipped_without_persisted_sim(monkeypatch):
    calls = []

    async def fake_create(**kw):
        calls.append(kw)

    monkeypatch.setattr(simulation_service, "create_center_suggestion", fake_create)
    await simulation_service._record_launch_suggestion(
        _request(),
        {"simulation_id": None, "aggregate": {"click_intent_rate": 1.0, "rejection_rate": 0.0}},
    )
    assert calls == []
