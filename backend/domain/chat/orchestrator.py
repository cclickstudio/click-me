# 채팅 오케스트레이터 — 매니지/시뮬/생성 서브에이전트를 도구로 부르는 LLM 라우터
"""build_chat_orchestrator(settings) → ask(ChatTurn) -> ChatAnswer | None.

키+실모드면 classify_intent → route → 도메인 서브에이전트(매니지·시뮬·생성) 또는 advise(일반 조언).
아니면 키워드 폴백(매니지만 처리, 그 외 None → chat.py가 기존 CLIO(Gemini)로 답).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from core.assistant import AssistantRequest
from domain.generator.assistant.agent import build_generator_agent
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.simulation.assistant.agent import build_simulation_agent

# 매니지먼트로 라우팅하는 키워드(폴백 전용) — 풀모드는 LLM이 도구 설명을 보고 스스로 판단한다.
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

# classify_intent 분류 프롬프트 — 질문을 도메인으로 라우팅(팀 구조: classify → route).
_CLASSIFY_SYSTEM = (
    "사용자 질문을 한 도메인으로 분류하라.\n"
    "- management: 집행된 광고의 성과·예산·소진·CTR·ROAS·캠페인 관리\n"
    "- simulation: 집행 전 시뮬레이션 결과·구매의도·클릭의향률·신뢰도·거부율·KPI 정의\n"
    "- generator: 광고 생성·카피 전략·시안·작성 원칙\n"
    "- advise: 그 외 일반 광고 전략·아이디어\n"
    "결과 ID(시뮬/생성 식별자)가 질문에 있으면 context_id로 함께 추출하라."
)

# advise(일반 조언) 프롬프트 — 도메인 도구 없이 직접 답.
_ADVISE_SYSTEM = (
    "너는 ClickMe의 수석 광고 전략 AI 어드바이저 CLIO다. 한국어로 간결하게 답한다.\n"
    "일반 광고 전략·해석·아이디어 질문에 도구 없이 직접 답한다. 문장 끝에 콜론을 쓰지 말 것."
)


@dataclass
class ChatTurn:
    """채팅 한 턴 입력 — 질문 + 직전 대화 + 광고 맥락."""

    question: str
    history: list[tuple[str, str]] = field(
        default_factory=list
    )  # (role, content), role=user|assistant
    ad_id: str | None = None


@dataclass
class ChatAnswer:
    """오케스트레이터 답변 — 본문 + 출처/근거 메타(SSE meta로 전달)."""

    answer: str
    meta: dict


def _is_management(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in _MGMT_KEYWORDS)


def _mgmt_answer(res: AskResult) -> str:
    """AskResult → 사용자 답변. 행동 제안이 있으면 승인 안내를 덧붙인다."""
    answer = res.answer
    if res.suggested_action:
        sa = res.suggested_action
        gate = "사람 승인 필요" if sa.requires_approval else "낮은 위험"
        answer += f"\n\n추천 조치: {sa.action_type} ({gate}) — 실행은 승인 화면에서 확인하세요."
    return answer


def _mgmt_meta(res: AskResult) -> dict:
    """AskResult → SSE meta(출처·인용·승인 게이트)."""
    return {
        "source": "management",
        "label": "매니지먼트 어시스턴트",
        "engine": "OpenAI · 실측+KB",
        "citations": [
            {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
        ],
        "used_tools": res.used_tools,
        "requires_approval": res.requires_approval,
        "thread_id": res.thread_id,
    }


def _assistant_meta(res, source: str, label: str) -> dict:
    """AssistantResult → SSE meta(출처·인용). 공통 계약 서브에이전트(시뮬·생성) 공용."""
    return {
        "source": source,
        "label": label,
        "engine": "OpenAI · 결과+KB",
        "citations": [
            {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
        ],
        "used_tools": res.used_tools,
    }


def build_chat_orchestrator(settings) -> Callable[[ChatTurn], Awaitable[ChatAnswer | None]]:
    """오케스트레이터 진입점. 키+실모드면 classify → route 그래프, 아니면 키워드 폴백."""
    api_key = getattr(settings, "openai_api_key", None)
    use_mock = getattr(settings, "use_mock", True)
    mgmt = build_management_agent(settings)  # 폴백/풀모드 자동 분기(같은 게이트)

    # ── 폴백 — 키워드로 매니지 질문만 라우팅, 일반 대화는 None(라우터가 Gemini로) ──
    if use_mock or not api_key:

        async def _ask_fallback(turn: ChatTurn) -> ChatAnswer | None:
            if not _is_management(turn.question):
                return None
            res = await mgmt(AskRequest(question=turn.question, ad_id=turn.ad_id))
            return ChatAnswer(answer=_mgmt_answer(res), meta=_mgmt_meta(res))

        return _ask_fallback

    # ── 풀모드 — classify_intent → route → 도메인 서브에이전트 / advise ──
    from typing import Literal, TypedDict  # noqa: PLC0415

    from langchain_core.messages import HumanMessage, SystemMessage  # noqa: PLC0415 — 키 있을 때만
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    from langgraph.graph import END, START, StateGraph  # noqa: PLC0415
    from pydantic import BaseModel  # noqa: PLC0415

    model_name = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.2, api_key=api_key)
    sim = build_simulation_agent(settings)  # 시뮬 서브에이전트(폴백/풀모드 자동)
    gen = build_generator_agent(settings)  # 생성 서브에이전트(폴백/풀모드 자동)

    # classify_intent 출력 스키마 — 도메인 분류 + 결과 식별자 추출.
    class _Intent(BaseModel):
        intent: Literal["management", "simulation", "generator", "advise"]
        context_id: str | None = None

    classifier = llm.with_structured_output(_Intent)

    # 그래프 상태 — 메시지 누적이 아니라 분류→답변 1패스. 노드엔 어노테이트하지 않는다.
    class _State(TypedDict, total=False):
        question: str
        intent: str
        context_id: str | None
        answer: str
        meta: dict

    async def classify(state) -> dict:
        res = await classifier.ainvoke(
            [SystemMessage(content=_CLASSIFY_SYSTEM), HumanMessage(content=state["question"])]
        )
        return {"intent": res.intent, "context_id": res.context_id}

    async def management_node(state) -> dict:
        res = await mgmt(
            AskRequest(question=state["question"], campaign_id=state.get("context_id"))
        )
        return {"answer": _mgmt_answer(res), "meta": _mgmt_meta(res)}

    async def simulation_node(state) -> dict:
        res = await sim(
            AssistantRequest(question=state["question"], context_id=state.get("context_id"))
        )
        return {
            "answer": res.answer,
            "meta": _assistant_meta(res, "simulation", "시뮬레이션 어시스턴트"),
        }

    async def generator_node(state) -> dict:
        res = await gen(
            AssistantRequest(question=state["question"], context_id=state.get("context_id"))
        )
        return {"answer": res.answer, "meta": _assistant_meta(res, "generator", "생성 어시스턴트")}

    async def advise_node(state) -> dict:
        resp = await llm.ainvoke(
            [SystemMessage(content=_ADVISE_SYSTEM), HumanMessage(content=state["question"])]
        )
        ans = resp.content if isinstance(resp.content, str) else ""
        return {
            "answer": ans,
            "meta": {"source": "orchestrator", "label": "CLIO", "engine": f"OpenAI · {model_name}"},
        }

    def route(state) -> str:
        return state.get("intent", "advise")

    g = StateGraph(_State)
    g.add_node("classify", classify)
    g.add_node("management", management_node)
    g.add_node("simulation", simulation_node)
    g.add_node("generator", generator_node)
    g.add_node("advise", advise_node)
    g.add_edge(START, "classify")
    g.add_conditional_edges(
        "classify",
        route,
        {
            "management": "management",
            "simulation": "simulation",
            "generator": "generator",
            "advise": "advise",
        },
    )
    for _node in ("management", "simulation", "generator", "advise"):
        g.add_edge(_node, END)
    graph = g.compile()

    async def _ask_full(turn: ChatTurn) -> ChatAnswer:
        # 1턴 = 1 트레이스 루트(classify → route → 서브에이전트).
        final = await graph.ainvoke(
            {"question": turn.question},
            config={
                "run_name": "assistant_chat",
                "tags": ["chat", "orchestrator"],
                "metadata": {"ad_id": turn.ad_id},
            },
        )
        meta = final.get("meta") or {
            "source": "orchestrator",
            "label": "CLIO",
            "engine": f"OpenAI · {model_name}",
        }
        return ChatAnswer(answer=final.get("answer", ""), meta=meta)

    return _ask_full
