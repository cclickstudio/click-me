# execute_from_simulation tool 골든 — improve_context 스텁으로 위젯 신호·안내 분기 검증(DB 미접근)
"""test_improve_tool.py와 동일하게 @tool 래퍼의 .coroutine으로 직접 호출한다."""

import pytest

from api.assistant import improve_context
from api.assistant.subagent_tools import build_chat_tools
from core.config import settings

_SRC = {
    "ad_title": "수분크림 광고",
    "ad_asset_url": "simulation/abc.png",
    "sample_size": 10,
    "aggregate": {
        "purchase_intent": 3.2,
        "rejection_rate": 0.08,
        "trust_avg": 3.5,
        "click_intent_rate": 0.042,
    },
    "plain_summary": None,
    "ranked_actions": [],
    "product_cutout_s3_key": None,
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
async def test_emits_exec_card_with_sim_values(tools, monkeypatch):
    captured = {}

    async def _fake(sid, org_id=None):
        captured["sid"] = sid
        return dict(_SRC)

    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    cmd = await tools["execute_from_simulation"].coroutine(
        simulation_id="sim-1", state=_state(), tool_call_id="t1"
    )
    w = cmd.update["widget"]
    assert w["type"] == "exec_from_sim"
    assert w["data"]["simulation_id"] == "sim-1"
    assert w["data"]["default_name"] == "수분크림 광고"
    assert w["data"]["click_intent_rate"] == 0.042
    assert w["data"]["rejection_rate"] == 0.08
    assert captured["sid"] == "sim-1"


@pytest.mark.asyncio
async def test_utterance_values_prefill_and_override_name(tools, monkeypatch):
    async def _fake(sid, org_id=None):
        return dict(_SRC)

    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    cmd = await tools["execute_from_simulation"].coroutine(
        simulation_id="sim-1",
        campaign_name="7월 프로모션",
        link_url="https://example.com",
        daily_budget_krw=20000,
        start_date="2026-07-10",
        state=_state(),
        tool_call_id="t1",
    )
    d = cmd.update["widget"]["data"]
    assert d["default_name"] == "7월 프로모션"  # 발화 이름이 시뮬 제목보다 우선
    assert d["link_url"] == "https://example.com"
    assert d["daily_budget_krw"] == 20000
    assert d["start_date"] == "2026-07-10"
    assert d["end_date"] is None


@pytest.mark.asyncio
async def test_auto_selects_latest_completed_and_records_history(tools, monkeypatch):
    # project_id가 있으면 spawn_record_execution이 DB 백그라운드 적재를 시도하므로
    # 스텁으로 막고(DB 미접근 유지) 호출 계약(요청 기록)만 고정한다.
    from domain.chat import helpers

    recorded = {}

    async def _latest(project_id):
        return "sim-latest" if project_id == "p1" else None

    async def _fake(sid, org_id=None):
        return dict(_SRC) if sid == "sim-latest" else None

    def _record(project_id, feature_type, action, summary, payload):
        recorded["project_id"] = project_id
        recorded["action"] = action

    monkeypatch.setattr(improve_context, "latest_completed_simulation_id", _latest)
    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    monkeypatch.setattr(helpers, "spawn_record_execution", _record)
    cmd = await tools["execute_from_simulation"].coroutine(
        state=_state(project_id="p1"), tool_call_id="t1"
    )
    assert cmd.update["widget"]["data"]["simulation_id"] == "sim-latest"
    assert recorded["action"] == "execute_from_simulation_request"
    assert recorded["project_id"] == "p1"


@pytest.mark.asyncio
async def test_no_project_no_sid_guides(tools):
    cmd = await tools["execute_from_simulation"].coroutine(state=_state(), tool_call_id="t1")
    assert "widget" not in cmd.update
    assert "프로젝트" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_no_completed_sim_guides(tools, monkeypatch):
    async def _latest(project_id):
        return None

    monkeypatch.setattr(improve_context, "latest_completed_simulation_id", _latest)
    cmd = await tools["execute_from_simulation"].coroutine(
        state=_state(project_id="p1"), tool_call_id="t1"
    )
    assert "widget" not in cmd.update
    assert "시뮬레이션" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_null_kpi_guides(tools, monkeypatch):
    async def _fake(sid, org_id=None):
        return {**_SRC, "aggregate": {**_SRC["aggregate"], "click_intent_rate": None}}

    monkeypatch.setattr(improve_context, "fetch_improve_source", _fake)
    cmd = await tools["execute_from_simulation"].coroutine(
        simulation_id="sim-1", state=_state(), tool_call_id="t1"
    )
    assert "widget" not in cmd.update
    assert "집계" in cmd.update["messages"][0].content
