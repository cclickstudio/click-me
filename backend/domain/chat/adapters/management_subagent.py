# 매니지먼트 서브에이전트 어댑터 — AskResult·SuggestedAction → SubAgentResult 매핑.
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from domain.chat.contracts.agent_io import Citation, ProposedAction, Route, SubAgentResult

if TYPE_CHECKING:
    from domain.chat.contracts.agent_io import SubAgentRequest


class ManagementSubAgent:
    """management/assistant 에이전트를 감싸는 서브에이전트 어댑터.

    ask: AskRequest → AskResult 코루틴.
    - ask=None 이면 사용 시점에 build_management_agent로 lazy-build.
    - 실행(execution) 브릿지는 이 어댑터의 범위 밖 — 제안(proposed_action)만 전달.
    """

    route: str = Route.MANAGEMENT

    def __init__(
        self,
        ask: Callable | None = None,
        settings: Any = None,
    ) -> None:
        self._ask = ask
        self._settings = settings

    def _get_ask(self) -> Callable:
        if self._ask is None:
            if self._settings is None:
                from core.config import settings as _settings

                self._settings = _settings
            from domain.management.assistant.agent import build_management_agent

            # build_management_agent는 ask 콜러블 자체를 반환(객체 아님 — 라우터도 직접 호출).
            self._ask = build_management_agent(self._settings)
        return self._ask

    async def run(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        try:
            return await self._dispatch(req)
        except Exception as exc:
            return SubAgentResult(route=Route.MANAGEMENT, error=str(exc))

    async def _dispatch(self, req: SubAgentRequest) -> SubAgentResult:  # type: ignore[name-defined]
        from domain.chat.adapters.history import history_to_preamble  # noqa: PLC0415
        from domain.management.assistant.contracts import AskRequest  # noqa: PLC0415

        ask = self._get_ask()
        ask_req = AskRequest(
            question=history_to_preamble(req.history) + req.question,
            campaign_id=req.context_ids.get("campaign_id"),
            ad_id=req.context_ids.get("ad_id"),
        )
        result = await ask(ask_req)

        citations = [
            Citation(kind=c.kind, source=c.source, title=c.title) for c in result.citations
        ]
        proposed = _to_proposed_action(result.suggested_action)

        return SubAgentResult(
            route=Route.MANAGEMENT,
            answer=result.answer,
            citations=citations,
            used_tools=list(result.used_tools),
            structured={},  # evidence는 디버그용 — SSE result 프레임에 노출하지 않음
            proposed_action=proposed,
        )


def _to_proposed_action(sa: Any) -> ProposedAction | None:
    """SuggestedAction → ProposedAction 변환. None 이면 None 반환.

    budget_after_krw·run_days는 SuggestedAction에 없어 기본값(None/7) — 집행 브릿지가 채운다.
    """
    if sa is None:
        return None
    return ProposedAction(
        action_type=sa.action_type,
        target_campaign_id=sa.target_campaign_id,
        tier=sa.tier,
        requires_approval=sa.requires_approval,
        rationale=sa.rationale,
    )
