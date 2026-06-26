# S3 — executor 단락 / 게이트 A / 핸드오프. S2 멀티스텝 execute_plan·build_plan·TurnContext 전제.
from dataclasses import dataclass

import pytest

from api.orchestration.context import TurnContext
from api.orchestration.executor import execute_plan
from api.orchestration.plan import PlanStep, make_plan
from api.orchestration.planner import build_plan
from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router


@dataclass
class _Img:
    s3_key: str
    kind: str = "image"


class _StartedAgent:
    domain = "generator"

    async def ask(self, ctx, step):
        return {"status": "started", "step_id": step.id, "task_id": "gen-1"}


class _SpyAgent:
    domain = "simulation"

    def __init__(self):
        self.calls = 0

    async def ask(self, ctx, step):
        self.calls += 1
        return {"simulation_id": "sim-1"}


@pytest.mark.asyncio
async def test_executor_short_circuits_on_started():
    spy = _SpyAgent()
    registry = AgentRegistry()
    registry.register(_StartedAgent())
    registry.register(spy)
    plan = make_plan(
        [
            PlanStep(domain="generator", action="generate", inputs={}),
            PlanStep(domain="simulation", action="simulate", inputs={}),
        ]
    )
    ctx = TurnContext(user_input="시안 만들고 시뮬 돌려줘")

    out = await execute_plan(plan, ctx, registry=registry)

    assert out["status"] == "started"
    assert spy.calls == 0  # generate started → simulate 미집행 (S3 한계 가드)


def _has_action(plan, action):
    return any(s.action == action for s in plan.steps)


def test_gate_a_attachment_forces_generate_step():
    # "봐줄래"는 어떤 도메인 키워드도 아님 → route.domain=clio, score 0.
    # 그래도 첨부 이미지가 있으면 generate 스텝이 들어간다(게이트 A).
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("이거 좀 봐줄래")
    plan = build_plan(route, query="이거 좀 봐줄래", attachments=(_Img("uploads/p.png"),))
    assert _has_action(plan, "generate")


def test_no_attachment_keeps_single_resolved_domain():
    # 첨부 없고 management만 해석 → 기존 단일 answer 스텝(회귀 0)
    route = Router([KeywordMatcher("management", frozenset({"캠페인"}))]).route("이번 캠페인 예산?")
    plan = build_plan(route, query="이번 캠페인 예산?")
    assert [s.action for s in plan.steps] == ["answer"]


def test_bootstrap_registers_real_generator_agent():
    from api.orchestration.bootstrap import build_orchestration
    from domain.generator.chat.domain_agent import GeneratorDomainAgent

    _, registry = build_orchestration(settings=object())
    agent = registry.get("generator")
    assert isinstance(agent, GeneratorDomainAgent)


def test_should_plan_true_when_image_attachment(monkeypatch):
    import api.routers.chat as chat
    from api.orchestration.registry import AgentRegistry
    from api.orchestration.routing import KeywordMatcher, Router

    router = Router([KeywordMatcher("management", frozenset({"캠페인"}))])
    registry = AgentRegistry()
    registry.register(_StartedAgent())  # domain="generator"
    monkeypatch.setattr(chat, "_orchestration", (router, registry))

    route = router.route("이거 좀 봐줄래")  # 키워드 없음 → score 0
    assert chat._should_plan(route, registry, has_image=True) is True
    assert chat._should_plan(route, registry, has_image=False) is False


def test_handoff_card_events_contain_stream_url():
    import api.routers.chat as chat

    handoff = {
        "status": "started",
        "task_id": "gen-1",
        "stream_url": "/api/generator/generations/gen-1/stream",
    }
    chunks = list(chat._handoff_card_events(handoff))
    joined = "".join(chunks)
    assert "gen-1" in joined
    assert "/api/generator/generations/gen-1/stream" in joined
