# Planner — RouteDecision으로 고정 Plan을 만든다(S2: 게이트 B면 멀티스텝, 아니면 단일)
from __future__ import annotations

from api.orchestration import policy
from api.orchestration.plan import Plan, PlanStep, make_plan
from api.orchestration.routing import RouteDecision


def build_plan(route: RouteDecision, *, query: str) -> Plan:
    if route.domain not in policy.DOMAIN_TO_ACTION:
        # build_plan은 도메인이 해석된 경우(route.score>0)에만 호출된다(chat._should_plan 가드).
        # 미해석(clio 등)으로 들어오면 조용한 KeyError 대신 명시적 실패(fail-loud).
        raise ValueError(
            f"build_plan: 미해석 도메인({route.domain}) — 호출 전 _should_plan 가드 필요"
        )
    nonzero = {c.domain for c in route.candidates if c.score > 0.0}
    sequential = any(marker in query for marker in policy.SEQUENTIAL_MARKERS)

    if len(nonzero) >= 2 or sequential:  # 게이트 B 진입
        steps = [
            PlanStep(domain=policy.ACTION_TO_DOMAIN[action], action=action, inputs={"query": query})
            for action in policy.PIPELINE_ORDER
            if policy.ACTION_TO_DOMAIN[action] in nonzero
        ]
        if len(steps) >= 2:  # 파이프라인 도메인 2개+ 매칭 시에만 멀티스텝
            return make_plan(steps)
        # 게이트 B지만 파이프라인 매칭 <2 → 아래 단일 스텝으로 fallback

    step = PlanStep(
        domain=route.domain,
        action=policy.DOMAIN_TO_ACTION[route.domain],
        inputs={"query": query},
    )
    return make_plan([step])
