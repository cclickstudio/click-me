# 시뮬레이션 서브에이전트 어댑터 — ReAct(자연어 질의)·읽기·트리거(비동기 시작) 매핑.
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from domain.chat.adapters import sim_tools
from domain.chat.contracts.agent_io import Citation, Route, SubAgentResult

if TYPE_CHECKING:
    from domain.chat.contracts.agent_io import SubAgentRequest

_UNSET = object()


class SimulationSubAgent:
    """SimulationService를 감싸는 서브에이전트 어댑터.

    - 풀모드(키 있음): sim_agent ReAct가 자연어 질문을 read 툴·KB로 답함.
    - 폴백(use_mock/키 없음): simulation_id면 집계 요약(인메모리 miss 시 DB 영속), ad_id면 트리거.
    - service/agent는 lazy-build (테스트는 fake 주입).
    """

    route: str = Route.SIMULATION

    def __init__(self, service: Any = None) -> None:
        self._service = service
        self._agent: Any = _UNSET

    def _get_service(self) -> Any:
        if self._service is None:
            from core.config import settings
            from domain.simulation.wiring import build_simulation_service

            self._service = build_simulation_service(settings)
        return self._service

    def _get_agent(self) -> Any:
        """ReAct 에이전트(풀모드) 또는 None(폴백). 1회 lazy-build."""
        if self._agent is _UNSET:
            from core.config import settings
            from domain.chat.adapters.sim_agent import build_simulation_agent

            self._agent = build_simulation_agent(settings)
        return self._agent

    async def run(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        try:
            return await self._dispatch(req)
        except Exception as exc:  # noqa: BLE001
            return SubAgentResult(route=Route.SIMULATION, error=str(exc))

    async def _dispatch(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        sim_id = req.context_ids.get("simulation_id")
        ad_id = req.context_ids.get("ad_id")

        # --- 트리거: 기존 시뮬 없이 ad_id만 → 비동기 시작(액션) ---
        if ad_id and not sim_id:
            return await self._start(req, ad_id)

        # --- 풀모드 ReAct: 자연어 질문을 read 툴 + KB로 답 ---
        agent = self._get_agent()
        if agent is not None:
            out = await agent(req.question, req.context_ids)
            sim_data = out.get("sim_data") or {}
            return SubAgentResult(
                route=Route.SIMULATION,
                answer=out.get("answer") or "결과를 가져왔어요.",
                citations=[
                    Citation(kind="kb", source=c.get("source", ""), title=c.get("title", ""))
                    for c in out.get("kb_citations", [])
                ],
                used_tools=list(out.get("used_tools", [])),
                structured=({"kind": "simulation_aggregate", "data": sim_data} if sim_data else {}),
            )

        # --- 폴백(키 없음/mock): 구조화 요약 ---
        if sim_id:
            return await self._fallback_read(sim_id)
        # id 없음 + org 맥락 있으면 조직 시뮬 현황 목록으로 안내(실 DB, LLM 불필요).
        org_id = req.context_ids.get("organization_id")
        if org_id:
            listing = await sim_tools.sim_list(limit=5, org_id=org_id)
            sims = listing.get("simulations") or []
            if sims:
                return SubAgentResult(
                    route=Route.SIMULATION,
                    answer=_build_sim_list_summary(sims),
                    structured={"kind": "simulation_list", "data": listing},
                )
        return SubAgentResult(
            route=Route.SIMULATION,
            answer="어떤 시뮬레이션이 궁금하신가요? 시뮬 이름이나 simulation_id를 알려주세요.",
        )

    async def _start(self, req: SubAgentRequest, ad_id: str) -> SubAgentResult:  # type: ignore[name-defined]
        from domain.simulation.contracts.schemas import SimulationRunRequest

        svc = self._get_service()
        sim_req = SimulationRunRequest(
            ad_id=ad_id,
            ad_content=req.knobs.get("ad_content"),
            ad_image_url=req.context_ids.get("ad_image_url"),  # 채팅 첨부 이미지(VLM 입력)
            ad_image_key=req.context_ids.get("ad_image_key"),  # S3 영구 식별자(DB 영속)
            sample_size=int(req.knobs.get("sample_size", 20)),
            project_id=req.context_ids.get("project_id"),
            organization_id=req.context_ids.get("organization_id"),
        )
        run_id: str = await svc.start(sim_req)
        return SubAgentResult(
            route=Route.SIMULATION,
            answer=(
                f"시뮬레이션을 시작했어요 (run_id: {run_id}). "
                "결과는 잠시 후 run_id로 다시 물어보세요."
            ),
        )

    async def _fallback_read(self, sim_id: str) -> SubAgentResult:
        """폴백 읽기 — 인메모리 결과 우선, miss면 DB 영속(sim_tools)으로 신뢰지표 제공."""
        svc = self._get_service()
        result = svc.get_result(sim_id)
        if result is not None:
            agg: dict = result.get("aggregate", {})
            return SubAgentResult(
                route=Route.SIMULATION,
                answer=_build_kpi_summary(agg),
                structured={"kind": "simulation_aggregate", "data": agg},
            )
        # 인메모리 miss(재시작 등) → DB 영속에서 복원.
        data = await sim_tools.sim_result(sim_id)
        if "error" in data:
            return SubAgentResult(
                route=Route.SIMULATION,
                answer="요청하신 시뮬레이션 결과를 찾지 못했어요. run_id를 다시 확인해 주세요.",
            )
        return SubAgentResult(
            route=Route.SIMULATION,
            answer=_build_kpi_summary(data),
            structured={"kind": "simulation_aggregate", "data": data},
        )


def _build_sim_list_summary(sims: list[dict]) -> str:
    """시뮬 현황 목록을 한국어 마크다운 요약으로(폴백·LLM 없음)."""
    lines = [f"현재 시뮬레이션 {len(sims)}건입니다."]
    for s in sims:
        title = s.get("ad_title") or "(제목 없음)"
        status = s.get("status") or "-"
        cir = (s.get("kpi") or {}).get("click_intent_rate")
        kpi_str = f", 클릭의향률 {cir:.1%}" if isinstance(cir, (int, float)) else ""
        sid = str(s.get("simulation_id") or "")[:8]
        lines.append(f"- {title} — {status}{kpi_str} (id: {sid})")
    return "\n".join(lines)


def _build_kpi_summary(agg: dict) -> str:
    """집계 딕셔너리에서 한국어 KPI 요약 문장을 생성한다."""
    lines = ["시뮬레이션 집계 결과입니다."]
    if agg.get("click_intent_rate") is not None:
        ci_low = agg.get("ci_low")
        ci_high = agg.get("ci_high")
        ci_str = (
            f" (신뢰구간 {ci_low:.2f}–{ci_high:.2f})"
            if ci_low is not None and ci_high is not None
            else ""
        )
        lines.append(f"- 클릭 의향률: {agg['click_intent_rate']:.1%}{ci_str}")
    if agg.get("purchase_intent") is not None:
        lines.append(f"- 구매의도: {agg['purchase_intent']:.1f} / 5점")
    if agg.get("trust_avg") is not None:
        lines.append(f"- 신뢰도: {agg['trust_avg']:.1f} / 5점")
    if agg.get("rejection_rate") is not None:
        lines.append(f"- 거부율: {agg['rejection_rate']:.1%}")
    if agg.get("effective_n") is not None:
        lines.append(f"- 유효표본수(effective_n): {agg['effective_n']:.0f}")
    return "\n".join(lines)
