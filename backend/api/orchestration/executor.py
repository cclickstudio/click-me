# Plan Executor — 고정 Plan의 스텝을 집행(S1: 단일 스텝만 허용, 멀티스텝은 후속 슬라이스)
from __future__ import annotations

from typing import Any

from api.orchestration.plan import Plan
from api.orchestration.registry import AgentRegistry


class PlanExecutionError(RuntimeError):
    """단일 스텝 위반·미등록 도메인 등 집행 불가 상태(조용한 폴백 금지)."""


async def execute_plan(plan: Plan, *, req: Any, registry: AgentRegistry) -> Any:
    # S1은 정확히 1스텝만 집행한다. 0개·2개+ 는 명시적 실패(멀티스텝 산출 전달은 후속 슬라이스).
    if len(plan.steps) != 1:
        raise PlanExecutionError(f"S1은 단일 스텝만 허용(받음: {len(plan.steps)}스텝)")
    step = plan.steps[0]
    agent = registry.get(step.domain)
    if agent is None:
        raise PlanExecutionError(f"미등록 도메인 스텝: {step.domain}")
    return await agent.ask(req)
