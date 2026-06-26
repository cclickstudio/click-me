# Planner — RouteDecision으로 고정 Plan을 만든다(S2: 게이트 B면 멀티스텝, 아니면 단일)
from __future__ import annotations

from api.orchestration import policy
from api.orchestration.plan import Plan, PlanStep, make_plan
from api.orchestration.routing import RouteDecision


def _has_image_attachment(attachments) -> bool:
    return any(getattr(a, "kind", None) == "image" for a in attachments)


def build_plan(route: RouteDecision, *, query: str, attachments: tuple = ()) -> Plan:
    has_image = _has_image_attachment(attachments)
    nonzero = {c.domain for c in route.candidates if c.score > 0.0}
    if has_image:
        nonzero.add("generator")  # 게이트 A — 첨부 이미지 → generate 보장
    if not nonzero:
        # 미해석 도메인 & 첨부 없음 — 호출 전 _should_plan 가드 필요(fail-loud)
        raise ValueError(
            f"build_plan: 미해석 도메인({route.domain})·첨부 없음 — _should_plan 가드 필요"
        )

    sequential = any(marker in query for marker in policy.SEQUENTIAL_MARKERS)
    if len(nonzero) >= 2 or sequential:  # 게이트 B 진입
        steps = [
            PlanStep(domain=policy.ACTION_TO_DOMAIN[action], action=action, inputs={"query": query})
            for action in policy.PIPELINE_ORDER
            if policy.ACTION_TO_DOMAIN[action] in nonzero
        ]
        if len(steps) >= 2:  # 파이프라인 도메인 2개+ 매칭 시에만 멀티스텝
            return make_plan(steps)
        # 게이트 B지만 매칭 <2 → 아래 단일 fallback

    # 단일 스텝 — 첨부 있으면 generator 우선(generate), 아니면 해석된 route.domain
    single = "generator" if has_image else route.domain
    step = PlanStep(domain=single, action=policy.DOMAIN_TO_ACTION[single], inputs={"query": query})
    return make_plan([step])
