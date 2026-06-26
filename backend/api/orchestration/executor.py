# Plan Executor — 고정 Plan의 스텝을 순차 집행, 산출을 블랙보드(step.id)에 누적(S2 멀티스텝)
from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from api.orchestration.context import TurnContext
from api.orchestration.plan import Plan, PlanStep
from api.orchestration.registry import AgentRegistry

try:  # LangSmith 미설치/비활성이어도 집행은 진행(트레이스만 생략).
    from langsmith import trace as _langsmith_trace
except Exception:  # noqa: BLE001
    _langsmith_trace = None


class PlanExecutionError(RuntimeError):
    """빈 Plan·미등록 도메인 등 집행 불가 상태(조용한 폴백 금지)."""


def _step_trace(step: PlanStep) -> Any:
    # 스텝별 트레이스 보장 — assistant.plan.step.{action}, tag=[assistant, domain].
    # turn 루트(assistant.chat.turn) 아래 각 스텝이 개별 자식 run으로 중첩된다.
    if _langsmith_trace is None:
        return nullcontext()
    return _langsmith_trace(
        name=f"assistant.plan.step.{step.action}", tags=["assistant", step.domain]
    )


async def execute_plan(plan: Plan, ctx: TurnContext, *, registry: AgentRegistry) -> Any:
    # 1스텝 이상 순차 집행. 0스텝·미등록은 명시적 실패(fail-loud).
    if not plan.steps:
        raise PlanExecutionError("빈 Plan은 집행할 수 없다")
    out: Any = None
    for step in plan.steps:
        agent = registry.get(step.domain)
        if agent is None:
            raise PlanExecutionError(f"미등록 도메인 스텝: {step.domain}")
        with _step_trace(step):  # 스텝별 트레이스 보장
            out = await agent.ask(ctx, step)
        ctx.results[step.id] = out  # 블랙보드 누적 — 다음 스텝이 output_of로 읽는다
    return out  # 마지막 스텝 산출
