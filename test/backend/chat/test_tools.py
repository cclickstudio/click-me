# tool 실행 골든 — DB 없이 위젯 tool의 Command(update) 검증(InjectedState는 직접 주입)
"""위젯 tool 호출 시 정확한 meta.widget·source를 상태에 적재함을 고정한다(LLM 라우팅 무관).

USE_MOCK=true(루트 conftest)라 서브에이전트는 fallback로 빌드되고, 위젯 tool은 DB를 타지 않는다
(project_id=None → spawn_persist 조기 반환). tool은 @tool 래퍼의 .coroutine으로 직접 호출한다.
"""

import pytest

from api.assistant.subagent_tools import build_chat_tools
from core.config import settings


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


async def _run(tools, tool_name, **kwargs):
    return await tools[tool_name].coroutine(state=_state(), tool_call_id="t1", **kwargs)


@pytest.mark.asyncio
async def test_run_simulation_emits_sim_form(tools):
    cmd = await _run(
        tools,
        "run_simulation",
        ad_content="여름 세일",
        ad_title="여름",
        product_category="",
        ad_objective="",
    )
    assert cmd.update["widget"] == {
        "type": "sim_form",
        "data": {
            "ad_title": "여름",
            "ad_content": "여름 세일",
            "product_category": None,
            "ad_objective": None,
        },
    }
    assert cmd.update["source"] == "simulation"


@pytest.mark.asyncio
async def test_run_generation_emits_gen_form(tools):
    cmd = await _run(tools, "run_generation", product_name="수분크림", target_audience="20대 여성")
    assert cmd.update["widget"]["type"] == "gen_form"
    assert cmd.update["widget"]["data"]["product_name"] == "수분크림"
    assert cmd.update["widget"]["data"]["target_audience"] == "20대 여성"
    assert cmd.update["source"] == "generator"


@pytest.mark.asyncio
async def test_run_generation_complete_args_asks_about_image_first(tools):
    # 완비돼도 이미지 의사 미확인이면 시작하지 않고 되묻는다(형태 없는 상품 배려)
    cmd = await tools["run_generation"].coroutine(
        state=_state(project_id="p1"),
        tool_call_id="t1",
        product_name="수분크림",
        product_description="산뜻한 수분 크림",
        target_audience="20대 여성",
    )
    assert "widget" not in cmd.update  # 생성 미시작 — 질문만
    assert "상품 이미지" in cmd.update["messages"][0].content


@pytest.mark.asyncio
async def test_run_generation_skip_image_starts_immediately(tools, monkeypatch):
    # 상품명·설명·타깃 + 프로젝트 완비 + 이미지 없이 확정 → 폼 없이 즉시 실행(진행 카드)
    import api.assistant.subagent_tools as st

    captured = {}

    async def _start(**kw):
        captured.update(kw)
        return {"generation_id": "g9", "stream_url": "/api/generator/generations/g9/stream"}

    monkeypatch.setattr(st, "start_generation_now", _start)
    cmd = await tools["run_generation"].coroutine(
        state=_state(project_id="p1"),
        tool_call_id="t1",
        product_name="수분크림",
        product_description="산뜻한 수분 크림",
        target_audience="20대 여성",
        skip_product_image=True,
    )
    assert cmd.update["widget"]["type"] == "gen_progress"
    assert cmd.update["widget"]["data"]["generation_id"] == "g9"
    assert "/stream" in cmd.update["widget"]["data"]["stream_url"]
    assert cmd.update["source"] == "generator"
    assert captured["project_id"] == "p1"
    assert captured["campaign_objective"] == "conversion"


@pytest.mark.asyncio
async def test_run_generation_with_attached_image_uses_form(tools):
    # 이번 턴 이미지 첨부 → 즉시 실행 대신 폼(첨부가 상품 이미지로 프리필됨)
    cmd = await tools["run_generation"].coroutine(
        state=_state(project_id="p1", has_image=True),
        tool_call_id="t1",
        product_name="수분크림",
        product_description="산뜻한 수분 크림",
        target_audience="20대 여성",
        skip_product_image=True,  # 첨부가 있으면 skip 지시보다 첨부 우선
    )
    assert cmd.update["widget"]["type"] == "gen_form"


@pytest.mark.asyncio
async def test_run_generation_complete_args_without_project_falls_back_to_form(tools):
    # 프로젝트 미선택이면 값이 완비돼도 폼(프로젝트 선택 포함) 폴백
    cmd = await _run(
        tools,
        "run_generation",
        product_name="수분크림",
        product_description="산뜻한 수분 크림",
        target_audience="20대 여성",
    )
    assert cmd.update["widget"]["type"] == "gen_form"


@pytest.mark.asyncio
async def test_create_campaign_maps_objective_and_budget(tools):
    cmd = await _run(tools, "create_campaign", name="", objective="leads", total_budget_krw=50000)
    assert cmd.update["widget"] == {
        "type": "create_campaign",
        "data": {"prefill": {"objective": "leads", "total_budget_krw": 50000}},
    }
    assert cmd.update["source"] == "deep-agent"


@pytest.mark.asyncio
async def test_create_campaign_drops_invalid_objective(tools):
    cmd = await _run(tools, "create_campaign", objective="invalid", total_budget_krw=0)
    # enum 밖 objective·0 예산은 prefill에서 제외
    assert cmd.update["widget"]["data"]["prefill"] == {}


@pytest.mark.asyncio
async def test_manage_campaign_pause(tools):
    cmd = await _run(tools, "manage_campaign", action="pause", campaign_name="여름세일")
    assert cmd.update["widget"]["type"] == "campaign_action"
    assert cmd.update["widget"]["data"]["action"] == {
        "action": "pause",
        "campaign_name": "여름세일",
    }
    assert cmd.update["source"] == "deep-agent"


@pytest.mark.asyncio
async def test_manage_campaign_invalid_action_no_widget(tools):
    cmd = await _run(tools, "manage_campaign", action="frobnicate")
    assert "widget" not in cmd.update


@pytest.mark.asyncio
async def test_batch_simulation(tools):
    cmd = await _run(tools, "batch_simulation")
    assert cmd.update["widget"] == {"type": "batch_sim_form"}
    assert cmd.update["source"] == "simulation"


@pytest.mark.asyncio
async def test_generate_report_period(tools):
    cmd = await _run(tools, "generate_report", period="month")
    assert cmd.update["widget"] == {
        "type": "report_ready",
        "data": {"project_id": None, "period": "month"},
    }
