# 슈퍼바이저 라우팅 — Claude tool-calling 또는 결정론 키워드 폴백.
from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from domain.chat.contracts.agent_io import Route

# chat.py에서 이관한 매니지먼트 키워드(원본 api/routers/chat.py _MGMT_KEYWORDS).
_MGMT_KEYWORDS: frozenset[str] = frozenset(
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

_SIM_KEYWORDS: frozenset[str] = frozenset(
    {
        "시뮬",
        "시뮬레이션",
        "반응",
        "구매의도",
        "신뢰도",
        "거부율",
        "클릭의향",
        "페르소나",
        "kpi",
        "예측 반응",
    }
)

_GEN_KEYWORDS: frozenset[str] = frozenset(
    {
        "시안",
        "생성",
        "카피",
        "이미지",
        "크리에이티브",
        "소재 만들",
        "광고 만들",
    }
)

_ROUTING_SYSTEM = (
    "너는 광고 플랫폼 챗의 라우터다. 사용자 요청 의도를 보고 도구 하나를 호출해 위임처를 정한다.\n"
    "- 캠페인·예산·성과·집행(일시중지/증액 등) → route_to_management\n"
    "- 광고 반응 예측·시뮬레이션·구매의도/신뢰도/거부율 KPI → route_to_simulation\n"
    "- 새 광고 시안·카피·이미지 생성 → route_to_generation\n"
    "- 그 외 일반 대화·전략 자문 → answer_directly\n"
    "반드시 도구 하나만 호출한다."
)


@tool
async def route_to_simulation(reason: str) -> str:
    """광고 반응 예측·시뮬레이션·KPI 조회 의도일 때."""
    return reason


@tool
async def route_to_generation(reason: str) -> str:
    """새 광고 시안·카피·이미지 생성 의도일 때."""
    return reason


@tool
async def route_to_management(reason: str) -> str:
    """캠페인·예산·성과·집행 의도일 때."""
    return reason


@tool
async def answer_directly(reason: str) -> str:
    """일반 대화·전략 자문 — 위임 없이 직접 답변."""
    return reason


_ROUTING_TOOLS = [route_to_simulation, route_to_generation, route_to_management, answer_directly]
_TOOL_TO_ROUTE: dict[str, Route] = {
    "route_to_simulation": Route.SIMULATION,
    "route_to_generation": Route.GENERATION,
    "route_to_management": Route.MANAGEMENT,
    "answer_directly": Route.GENERAL,
}


def _last_user_text(messages: list) -> str:
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            return m.content if isinstance(m.content, str) else str(m.content)
    return ""


def keyword_route(text: str) -> Route:
    """결정론 폴백 — 키워드 매칭.
    우선순위: 시뮬 > 생성 > 매니지먼트 > general.
    시뮬/생성을 먼저 체크해 "광고 시뮬" 같이 mgmt 키워드("광고")와 겹치는 문장을 올바르게 분류.
    """
    low = text.lower()
    if any(k in low for k in _SIM_KEYWORDS):
        return Route.SIMULATION
    if any(k in low for k in _GEN_KEYWORDS):
        return Route.GENERATION
    if any(k in low for k in _MGMT_KEYWORDS):
        return Route.MANAGEMENT
    return Route.GENERAL


async def decide_route(messages: list, llm) -> Route:
    """라우트 결정 — llm None이면 키워드, 있으면 tool-calling."""
    if llm is None:
        return keyword_route(_last_user_text(messages))
    bound = llm.bind_tools(_ROUTING_TOOLS)
    ai: AIMessage = await bound.ainvoke([SystemMessage(content=_ROUTING_SYSTEM), *messages])
    calls = getattr(ai, "tool_calls", None) or []
    if calls:
        return _TOOL_TO_ROUTE.get(calls[0]["name"], Route.GENERAL)
    return Route.GENERAL
