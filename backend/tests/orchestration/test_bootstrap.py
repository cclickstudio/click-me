# bootstrap — 어댑터 ctx 계약 만족 + gen/sim 등록·라우팅(빌더는 stub)
import pytest

import api.orchestration.bootstrap as bootstrap
from api.orchestration.bootstrap import (
    MGMT_KEYWORDS,
    GeneratorStubAgent,
    ManagementDomainAgent,
    SimulationStubAgent,
    build_orchestration,
)
from api.orchestration.context import TurnContext
from api.orchestration.plan import PlanStep


def _patch_builder(monkeypatch):
    # 실제 management 에이전트 빌드를 우회 — composition root는 '등록'만 검증한다.
    async def _echo_ask(req):
        return req

    monkeypatch.setattr(bootstrap, "build_management_agent", lambda settings: _echo_ask)


@pytest.mark.asyncio
async def test_management_adapter_translates_ctx_to_ask_request():
    captured = {}

    async def _ask(req):
        captured["req"] = req
        return req

    agent = ManagementDomainAgent(_ask)
    ctx = TurnContext(user_input="캠페인 예산", session_id="s1", ad_id="ad-7")
    step = PlanStep(domain="management", action="answer", inputs={"query": "캠페인 예산"})

    result = await agent.ask(ctx, step)

    assert agent.domain == "management"
    assert captured["req"].question == "캠페인 예산"
    assert captured["req"].ad_id == "ad-7"
    assert captured["req"].thread_id == "mgmt-s1"
    assert result is captured["req"]


@pytest.mark.asyncio
async def test_generator_stub_returns_ad_id_deterministically():
    agent = GeneratorStubAgent()
    ctx = TurnContext(user_input="시안 만들어")
    step = PlanStep(domain="generator", action="generate", inputs={})
    a = await agent.ask(ctx, step)
    b = await GeneratorStubAgent().ask(TurnContext(user_input="시안 만들어"), step)
    assert a["ad_id"] == b["ad_id"]  # 같은 입력 → 같은 ad_id(결정론)
    assert a["ad_id"].startswith("stub-ad-")


@pytest.mark.asyncio
async def test_simulation_stub_reads_generate_ad_id_from_blackboard():
    ctx = TurnContext(user_input="시뮬 돌려")
    ctx.results["generate-1"] = {"ad_id": "ad-42"}
    out = await SimulationStubAgent().ask(
        ctx, PlanStep(domain="simulation", action="simulate", inputs={})
    )
    assert out["ad_id"] == "ad-42"
    assert "kpi" in out


def test_build_orchestration_registers_and_routes_three_domains(monkeypatch):
    _patch_builder(monkeypatch)
    router, registry = build_orchestration(settings=object())
    assert router.route("이번 캠페인 예산 어때").domain == "management"
    assert router.route("시안 만들어줘").domain == "generator"
    assert router.route("시뮬 돌려줘").domain == "simulation"
    assert registry.get("management") is not None
    assert registry.get("generator").domain == "generator"
    assert registry.get("simulation").domain == "simulation"


def test_build_orchestration_non_keyword_is_default(monkeypatch):
    _patch_builder(monkeypatch)
    router, _ = build_orchestration(settings=object())
    assert router.route("안녕하세요").domain == "clio"


def test_mgmt_keywords_nonempty():
    assert "캠페인" in MGMT_KEYWORDS and len(MGMT_KEYWORDS) >= 10
