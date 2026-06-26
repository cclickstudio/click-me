# 오케스트레이션 합성 루트 — 매처·도메인 에이전트 등록(여기서만 도메인 내부 import 허용)
from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable

from api.orchestration.registry import AgentRegistry
from api.orchestration.routing import KeywordMatcher, Router
from domain.generator.chat.domain_agent import GeneratorDomainAgent
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

# generator/simulation 라우팅 키워드(도메인 소유 분리는 후속).
GEN_KEYWORDS: frozenset[str] = frozenset({"시안", "생성", "만들어", "제작", "크리에이티브", "카피"})
SIM_KEYWORDS: frozenset[str] = frozenset({"시뮬", "시뮬레이션", "반응", "예측", "테스트", "검증"})


def _stub_id(prefix: str, seed: str) -> str:
    # 결정론 더미 id — builtin hash()는 PYTHONHASHSEED 의존이라 금지, sha1로 안정화.
    return f"{prefix}-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:8]}"


class ManagementDomainAgent:
    """기존 build_management_agent(함수 반환)를 DomainAgent 계약으로 감싸는 어댑터."""

    domain = "management"

    def __init__(self, ask: Callable[[AskRequest], Awaitable[AskResult]]) -> None:
        self._ask = ask

    async def ask(self, ctx, step) -> AskResult:
        # 블랙보드 ctx/step → 기존 AskRequest로 번역(단일 계약, 출력은 S1과 동일).
        question = step.inputs.get("query") or ctx.user_input
        thread_id = f"mgmt-{ctx.session_id}" if ctx.session_id else None
        req = AskRequest(question=question, ad_id=ctx.ad_id, thread_id=thread_id)
        return await self._ask(req)


class SimulationStubAgent:
    """simulation 스텁 — 블랙보드에서 generate ad_id를 읽어 KPI 더미 반환(실 KPI·게이트는 S4)."""

    domain = "simulation"

    async def ask(self, ctx, step) -> dict:
        upstream = ctx.output_of("generate")
        ad_id = upstream["ad_id"] if upstream else None
        return {
            "simulation_id": _stub_id("stub-sim", str(ad_id)),
            "ad_id": ad_id,
            "kpi": {"click_intent": [0.10, 0.22], "reject_rate": 0.18},
        }


def build_orchestration(settings) -> tuple[Router, AgentRegistry]:
    """라우터 + 레지스트리를 합성한다. 도메인 추가 = 여기 매처/에이전트 한 줄."""
    router = Router(
        [
            KeywordMatcher("management", MGMT_KEYWORDS),
            KeywordMatcher("generator", GEN_KEYWORDS),
            KeywordMatcher("simulation", SIM_KEYWORDS),
        ]
    )
    registry = AgentRegistry()
    registry.register(ManagementDomainAgent(build_management_agent(settings)))
    registry.register(GeneratorDomainAgent())
    registry.register(SimulationStubAgent())
    return router, registry
