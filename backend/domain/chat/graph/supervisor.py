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
    "- 캠페인·예산·성과·소진·집행(일시중지/증액 등) 조회·실행 → route_to_management\n"
    "- 광고 반응 예측·시뮬레이션 실행·구매의도/신뢰도/거부율 KPI·페르소나 근거·시뮬 결과 조회 "
    "→ route_to_simulation\n"
    "- 새 광고 시안·카피·이미지 생성, 그리고 '내가/우리가 생성한' 시안·생성물의 "
    "목록·개수·상세·상태 조회 → route_to_generation\n"
    "- 그 외 일반 대화·전략 자문 → answer_directly\n"
    "주의: '몇 개/목록/내가 만든·생성한'이 생성물(시안)을 가리키면 캠페인(management)이 아니라 "
    "route_to_generation 이다.\n"
    "행동·능력 의도: 사용자가 특정 기능을 '해줘/만들어/돌려/실행/보여줘' 또는 "
    "'할 수 있냐/하려는데/어떻게'라고 물으면, 일반 대화로 보지 말고 해당 기능 "
    "에이전트로 라우팅한다(그 에이전트가 실행·안내). 예: '광고 생성해줘'·"
    "'이걸로 생성 할 수 있어?'·'광고 만들려는데 가능?' → route_to_generation, "
    "'이 광고로 시뮬 돌려'·'시뮬 가능?' → route_to_simulation.\n"
    "연속성: 직전 어시스턴트가 특정 기능의 진행/되물음(예: 시뮬 표본·타깃·제목 확인, "
    "생성 상품명 확인)이고 이번 사용자 메시지가 그에 대한 답·확인·되물음"
    "(예: '50명', '그냥 기본', '제목도 필요해?')이면, 새 의도로 보지 말고 "
    "그 기능과 같은 위임처로 라우팅한다.\n"
    "반드시 도구 하나만 호출한다."
)


def _capability_block(capabilities: dict | None) -> str:
    """역량 카탈로그를 라우팅 시스템 프롬프트에 붙일 블록으로(레지스트리 단일 진실원천)."""
    if not capabilities:
        return ""
    lines = [f"- {c.get('label')}: {c.get('does')}" for c in capabilities.values()]
    return "\n[역량 카탈로그]\n" + "\n".join(lines)


def _identity_block(identity: dict | None) -> str:
    """신원 스코프·현재 맥락 엔티티를 한 줄 블록으로(라우팅 판단 보조, 값 노출 아님)."""
    if not identity:
        return ""
    scope = [k for k in ("organization_id", "user_id", "project_id") if identity.get(k)]
    ents = [
        k for k in ("simulation_id", "campaign_id", "ad_id", "generation_id") if identity.get(k)
    ]
    parts = [f"신원 스코프: {'·'.join(scope) if scope else '없음(무인증/전역)'}"]
    if ents:
        parts.append(f"현재 맥락 엔티티: {'·'.join(ents)}")
    return "\n[맥락] " + " / ".join(parts)


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


# 결정론 라우팅 가드 강신호 — "조회 의도동사" + "도메인 명사" 페어로만 발동(대칭 오분류 방지).
_COUNT_WORDS = ("몇 개", "몇개", "몇 건", "목록", "개수", "갯수", "카운트", "리스트", "얼마나")
_GEN_NOUNS = ("생성", "시안", "제너레이터", "크리에이티브", "만든", "만들었")
_MGMT_NOUNS = ("캠페인", "예산", "성과", "소진", "집행", "게재")


def apply_route_guard(route: Route, text: str) -> Route:
    """라우트 위 결정론 보정 — '생성물 목록/개수'=GENERATION, '캠페인 목록/개수'=MANAGEMENT.

    대칭 오분류('캠페인 몇개'→GEN)를 막기 위해 조회동사 + 한쪽 도메인 명사만 매칭될 때만 보정한다
    (둘 다/둘 다 아님=모호 → 원 라우트 존중, LLM 신뢰).
    """
    low = text.lower()
    if not any(w in low for w in _COUNT_WORDS):
        return route
    gen = any(n in low for n in _GEN_NOUNS)
    mgmt = any(n in low for n in _MGMT_NOUNS)
    if gen and not mgmt:
        return Route.GENERATION
    if mgmt and not gen:
        return Route.MANAGEMENT
    return route


async def decide_route(messages: list, llm, *, capabilities=None, identity=None) -> Route:
    """라우트 결정 — llm None이면 키워드 폴백, 있으면 역량·신원 맥락을 주입한 정책 tool-calling.

    capabilities(레지스트리)·identity(신원/엔티티)는 라우팅 프롬프트에 보조 맥락으로 주입된다.
    산출은 단일 Route(불변) — SSE·그래프 위상 무영향.
    """
    text = _last_user_text(messages)
    if llm is None:
        return apply_route_guard(keyword_route(text), text)
    bound = llm.bind_tools(_ROUTING_TOOLS)
    system = _ROUTING_SYSTEM + _capability_block(capabilities) + _identity_block(identity)
    ai: AIMessage = await bound.ainvoke([SystemMessage(content=system), *messages])
    calls = getattr(ai, "tool_calls", None) or []
    route = _TOOL_TO_ROUTE.get(calls[0]["name"], Route.GENERAL) if calls else Route.GENERAL
    return apply_route_guard(route, text)
