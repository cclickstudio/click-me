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
