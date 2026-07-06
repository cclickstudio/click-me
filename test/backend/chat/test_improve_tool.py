# run_improvement tool 골든 — improve_context를 스텁해 위젯 신호·안내 분기 검증(DB 미접근)
"""test_tools.py와 동일하게 @tool 래퍼의 .coroutine으로 직접 호출한다."""

import pytest

from api.assistant import improve_context
from api.assistant.subagent_tools import build_chat_tools
from core.config import settings

_GEN_DATA = {
    "mode": "improve",
    "product_name": "수분크림",
    "simulation_summary": "표본 10명 · 구매의향 3.20/5",
    "plain_summary": None,
    "improvement_direction": "",
    "existing_ad_s3_key": None,
    "fix_requests": None,
    "target_audience": "",
    "campaign_objective": "conversion",
}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in build_chat_tools(settings)}


def _state(**kw):
    base = {
        "project_id": None,
        "session_id": "t",
        "user_id": None,
        "org_id": None,
        "messages": [],
    }
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_run_improvement_emits_improve_gen_form(tools, monkeypatch):
    captured = {}

    async def _fake(sid, fix_requests=None, org_id=None):
        captured["sid"] = sid
        captured["fix"] = fix_requests
        return dict(_GEN_DATA)

    monkeypatch.setattr(improve_context, "improve_gen_data_for_simulation", _fake)
    cmd = await tools["run_improvement"].coroutine(
        simulation_id="sim-1", state=_state(), tool_call_id="t1"
    )
    assert cmd.update["widget"]["type"] == "gen_form"
    assert cmd.update["widget"]["data"]["mode"] == "improve"
    assert cmd.update["source"] == "generator"
    assert captured["sid"] == "sim-1"


@pytest.mark.asyncio
async def test_run_improvement_auto_selects_latest_and_starts(tools, monkeypatch):
    # 프리필 완비 + 프로젝트 → 폼 없이 즉시 실행(진행 카드)
    import api.assistant.subagent_tools as st

    captured = {}

    async def _latest(project_id):
        return "sim-latest" if project_id == "p1" else None

    async def _fake(sid, fix_requests=None, org_id=None):
        return dict(_GEN_DATA) if sid == "sim-latest" else None

    async def _start(gen_data, project_id=None, created_by=None):
        captured["gen_data"] = gen_data
        captured["project_id"] = project_id
        return {"generation_id": "g7", "stream_url": "/api/generator/generations/g7/stream"}

    monkeypatch.setattr(improve_context, "latest_completed_simulation_id", _latest)
    monkeypatch.setattr(improve_context, "improve_gen_data_for_simulation", _fake)
    monkeypatch.setattr(st, "start_improve_generation", _start)
    cmd = await tools["run_improvement"].coroutine(state=_state(project_id="p1"), tool_call_id="t1")
    assert cmd.update["widget"]["type"] == "gen_progress"
    assert cmd.update["widget"]["data"]["generation_id"] == "g7"
    assert captured["project_id"] == "p1"
    assert captured["gen_data"]["mode"] == "improve"


@pytest.mark.asyncio
async def test_run_improvement_incomplete_prefill_falls_back_to_form(tools, monkeypatch):
    # simulation_summary가 비면 즉시 실행 대신 개선 폼 폴백
    async def _fake(sid, fix_requests=None, org_id=None):
        return {**_GEN_DATA, "simulation_summary": ""}

    monkeypatch.setattr(improve_context, "improve_gen_data_for_simulation", _fake)
    cmd = await tools["run_improvement"].coroutine(
        simulation_id="sim-1", state=_state(project_id="p1"), tool_call_id="t1"
    )
    assert cmd.update["widget"]["type"] == "gen_form"


@pytest.mark.asyncio
async def test_run_improvement_no_project_no_sid_guides(tools):
    cmd = await tools["run_improvement"].coroutine(state=_state(), tool_call_id="t1")
    assert "widget" not in cmd.update
    assert "프로젝트" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_run_improvement_no_completed_sim_guides(tools, monkeypatch):
    async def _latest(project_id):
        return None

    monkeypatch.setattr(improve_context, "latest_completed_simulation_id", _latest)
    cmd = await tools["run_improvement"].coroutine(state=_state(project_id="p1"), tool_call_id="t1")
    assert "widget" not in cmd.update
    assert "시뮬레이션" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_run_improvement_passes_fix_requests(tools, monkeypatch):
    captured = {}

    async def _fake(sid, fix_requests=None, org_id=None):
        captured["fix"] = fix_requests
        return dict(_GEN_DATA)

    monkeypatch.setattr(improve_context, "improve_gen_data_for_simulation", _fake)
    await tools["run_improvement"].coroutine(
        simulation_id="sim-1", fix_requests="가격 빼줘", state=_state(), tool_call_id="t1"
    )
    assert captured["fix"] == "가격 빼줘"
