# 시뮬레이션 서브에이전트 어댑터 — 읽기(결과 조회)·트리거(비동기 시작) 매핑.
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.chat.contracts.agent_io import Route, SubAgentResult

if TYPE_CHECKING:
    from domain.chat.contracts.agent_io import SubAgentRequest


class SimulationSubAgent:
    """SimulationService를 감싸는 서브에이전트 어댑터.

    - context_ids["simulation_id"] 있으면 읽기(get_result)
    - 아니면 context_ids["ad_id"]로 트리거(비동기 start, run_id 안내)
    - 둘 다 없으면 graceful error(ad_id 필요 안내)
    - service=None 이면 실제 사용 시점에 lazy-build (테스트는 fake 주입).
    """

    route: str = Route.SIMULATION

    def __init__(self, service: Any = None) -> None:
        self._service = service

    def _get_service(self) -> Any:
        if self._service is None:
            from core.config import settings
            from domain.simulation.wiring import build_simulation_service

            self._service = build_simulation_service(settings)
        return self._service

    async def run(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        try:
            return await self._dispatch(req)
        except Exception as exc:
            return SubAgentResult(route=Route.SIMULATION, error=str(exc))

    async def _dispatch(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        svc = self._get_service()
        simulation_id = req.context_ids.get("simulation_id")

        # --- 읽기 경로: 기존 run_id로 결과 조회 ---
        if simulation_id:
            result = svc.get_result(simulation_id)
            if result is None:
                return SubAgentResult(
                    route=Route.SIMULATION,
                    answer="요청하신 시뮬레이션 결과를 찾지 못했어요. run_id를 다시 확인해 주세요.",
                )
            agg: dict = result.get("aggregate", {})
            answer = _build_kpi_summary(agg)
            return SubAgentResult(
                route=Route.SIMULATION,
                answer=answer,
                structured={"kind": "simulation_aggregate", "data": agg},
            )

        # --- 트리거 경로: 새 시뮬레이션 비동기 시작 ---
        ad_id = req.context_ids.get("ad_id")
        if not ad_id:
            return SubAgentResult(
                route=Route.SIMULATION,
                error=(
                    "시뮬레이션을 시작하려면 ad_id가 필요해요. context_ids에 ad_id를 전달해 주세요."
                ),
            )

        from domain.simulation.contracts.schemas import SimulationRunRequest

        sim_req = SimulationRunRequest(
            ad_id=ad_id,
            ad_content=req.knobs.get("ad_content"),
            sample_size=int(req.knobs.get("sample_size", 20)),
            project_id=req.context_ids.get("project_id"),
        )
        run_id: str = await svc.start(sim_req)
        return SubAgentResult(
            route=Route.SIMULATION,
            answer=(
                f"시뮬레이션을 시작했어요 (run_id: {run_id}). "
                "결과는 잠시 후 run_id로 다시 물어보세요."
            ),
        )


def _build_kpi_summary(agg: dict) -> str:
    """집계 딕셔너리에서 한국어 KPI 요약 문장을 생성한다."""
    lines = ["시뮬레이션 집계 결과입니다."]
    if "click_intent_rate" in agg:
        ci_low = agg.get("ci_low")
        ci_high = agg.get("ci_high")
        ci_str = (
            f" (신뢰구간 {ci_low:.2f}–{ci_high:.2f})"
            if ci_low is not None and ci_high is not None
            else ""
        )
        lines.append(f"- 클릭 의향률: {agg['click_intent_rate']:.1%}{ci_str}")
    if "purchase_intent" in agg:
        lines.append(f"- 구매의도: {agg['purchase_intent']:.1f} / 5점")
    if "trust_avg" in agg:
        lines.append(f"- 신뢰도: {agg['trust_avg']:.1f} / 5점")
    if "rejection_rate" in agg:
        lines.append(f"- 거부율: {agg['rejection_rate']:.1%}")
    return "\n".join(lines)
