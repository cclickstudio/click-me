# Planner 셸 — RouteDecision으로 고정 Plan을 만든다(S1: 단일 도메인 1스텝)
from __future__ import annotations

from api.orchestration.plan import Plan, PlanStep, make_plan
from api.orchestration.routing import RouteDecision


def build_plan(route: RouteDecision, *, query: str) -> Plan:
    # S1: 해석된 도메인으로 1스텝 Plan. CLIO 분기·멀티스텝 LLM 분해는 호출자/후속 슬라이스.
    step = PlanStep(domain=route.domain, action="answer", inputs={"query": query})
    return make_plan([step])
