# 오케스트레이션 합성 루트 — 매처·도메인 에이전트 등록(여기서만 도메인 내부 import 허용)
from __future__ import annotations

from collections.abc import Awaitable, Callable

from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult

# 매니지먼트 라우팅 키워드(기존 chat.py에서 이전). 향후 도메인 소유로 분리 가능.
MGMT_KEYWORDS: frozenset[str] = frozenset(
    {
        "캠페인",
        "예산",
        "소진",
        "런레이트",
        "페이싱",
        "게재",
        "광고",
        "ctr",
        "roas",
        "cvr",
        "클릭률",
        "노출",
        "지출",
        "리드",
        "성과",
        "전환",
        "잔액",
        "일시중지",
        "멈춰",
        "증액",
        "감액",
        "소재",
        "예측대로",
        "매니지먼트",
    }
)


class ManagementDomainAgent:
    """기존 build_management_agent(함수 반환)를 DomainAgent 계약으로 감싸는 어댑터."""

    domain = "management"

    def __init__(self, ask: Callable[[AskRequest], Awaitable[AskResult]]) -> None:
        self._ask = ask

    async def ask(self, req: AskRequest) -> AskResult:
        return await self._ask(req)


def build_orchestration(settings) -> tuple[Router, AgentRegistry]:
    """라우터 + 레지스트리를 합성한다. 도메인 추가 = 여기 매처/에이전트 한 줄."""
    router = Router([KeywordMatcher("management", MGMT_KEYWORDS)])
    registry = AgentRegistry()
    registry.register(ManagementDomainAgent(build_management_agent(settings)))
    return router, registry
