# S3 — executor 단락 / 게이트 A / 핸드오프. S2 멀티스텝 execute_plan·build_plan·TurnContext 전제.
from dataclasses import dataclass

import pytest

from api.orchestration.context import TurnContext
from api.orchestration.executor import execute_plan
from api.orchestration.plan import PlanStep, make_plan
from api.orchestration.registry import AgentRegistry


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
