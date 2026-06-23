# 채팅 오케스트레이터 — 매니지/시뮬/생성 서브에이전트를 도구로 부르는 LLM 라우터
"""build_chat_orchestrator(settings) → ask(ChatTurn) -> ChatAnswer | None.

키+실모드면 OpenAI ReAct 그래프(LLM이 도구로 서브에이전트에 위임), 아니면 키워드 폴백.
지금은 매니지먼트 서브에이전트만 도구로 등록(끝-to-끝 최소 연결).
시뮬·생성은 같은 방식으로 추가한다.
폴백에서 매니지 질문이 아니면 None을 반환하고, 라우터(chat.py)가 기존 CLIO(Gemini)로 답한다.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.simulation.assistant.agent import build_simulation_agent
from domain.simulation.assistant.contracts import SimAskRequest

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

# 풀모드 오케스트레이터 시스템 프롬프트 — CLIO 페르소나 + 도구 위임 규칙.
_ORCHESTRATOR_SYSTEM = (
    "너는 ClickMe의 수석 광고 전략 AI 어드바이저 CLIO다. 한국어로 간결하게 답한다.\n"
    "광고 캠페인의 성과·예산·집행·게재 상태·전환 등 '집행된 광고 관리' 질문이면 "
    "ask_management 도구로 매니지먼트 어시스턴트에 위임하고, "
    "그 결과(실측 숫자)를 그대로 인용해 답한다.\n"
    "그 외 일반 광고 전략·해석·아이디어 질문은 도구 없이 직접 답한다.\n"
    "도구가 돌려준 숫자만 인용하고 추정·환각하지 않는다. 문장 끝에 콜론을 쓰지 말 것."
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


def _sim_meta(res) -> dict:
    """SimAskResult → SSE meta(출처·인용)."""
    return {
        "source": "simulation",
        "label": "시뮬레이션 어시스턴트",
        "engine": "OpenAI · 결과+KB",
        "citations": [
            {"kind": c.kind, "source": c.source, "title": c.title} for c in res.citations
        ],
        "used_tools": res.used_tools,
    }


def build_chat_orchestrator(settings) -> Callable[[ChatTurn], Awaitable[ChatAnswer | None]]:
    """오케스트레이터 진입점. 키+실모드면 OpenAI ReAct, 아니면 키워드 폴백."""
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

    # ── 풀모드 — OpenAI ReAct, 매니지먼트를 도구로 위임 ──
    from langchain_core.messages import (  # noqa: PLC0415 — 키 있을 때만 로드
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.tools import tool  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: PLC0415

    model_name = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model_name, temperature=0.2, api_key=api_key)
    sim = build_simulation_agent(settings)  # 시뮬 서브에이전트(폴백/풀모드 자동)

    @tool
    async def ask_management(question: str, campaign_id: str | None = None) -> dict:
        """집행된 광고의 성과·예산·집행·게재 상태 질문에 실측 데이터로 답한다.
        캠페인·예산·소진·CTR·ROAS·전환·게재 등 운영 관리 질문에 쓴다."""
        res = await mgmt(AskRequest(question=question, campaign_id=campaign_id))
        return {"_answer": _mgmt_answer(res), "_meta": _mgmt_meta(res)}

    @tool
    async def ask_simulation(question: str, simulation_id: str | None = None) -> dict:
        """집행 전 AI 가상 소비자 시뮬레이션의 결과 해석·KPI 정의·방법론 질문에 답한다.
        구매의도·클릭의향률·신뢰도·거부율·시뮬 결과 해석·"신뢰해도 되나"에 쓴다."""
        res = await sim(SimAskRequest(question=question, simulation_id=simulation_id))
        return {"_answer": res.answer, "_meta": _sim_meta(res)}

    bound = llm.bind_tools([ask_management, ask_simulation])
    _subagents = {"ask_management": ask_management, "ask_simulation": ask_simulation}

    class _State(MessagesState, total=False):
        tool_meta: dict | None
        rounds: int

    # 노드 시그니처에 _State(로컬 클래스)를 어노테이트하지 않는다 —
    # from __future__ annotations로 문자열화돼 langgraph가 런타임에 해석 못 함(NameError).
    async def agent(state) -> dict:
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=_ORCHESTRATOR_SYSTEM), *msgs]
        # 라운드 상한(3) 초과 시 도구 없는 LLM으로 최종 답 강제(무한 루프 방지)
        chosen = bound if state.get("rounds", 0) < 3 else llm
        return {"messages": [await chosen.ainvoke(msgs)]}

    async def tools_node(state) -> dict:
        ai = state["messages"][-1]
        tool_meta = state.get("tool_meta")
        out: list[ToolMessage] = []
        for call in ai.tool_calls:
            fn = _subagents.get(call["name"])
            if fn is None:
                continue
            payload = await fn.ainvoke(call.get("args", {}))
            tool_meta = payload.get("_meta")
            # LLM에는 답변 본문만 돌려준다(메타는 state에 보관해 SSE로 전달).
            out.append(
                ToolMessage(
                    content=json.dumps({"answer": payload.get("_answer", "")}, ensure_ascii=False),
                    tool_call_id=call["id"],
                )
            )
        return {"messages": out, "tool_meta": tool_meta, "rounds": state.get("rounds", 0) + 1}

    def route(state) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    g = StateGraph(_State)
    g.add_node("agent", agent)
    g.add_node("tools", tools_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    graph = g.compile()

    async def _ask_full(turn: ChatTurn) -> ChatAnswer:
        history = [
            HumanMessage(content=c) if role == "user" else AIMessage(content=c)
            for role, c in turn.history
        ]
        final = await graph.ainvoke(
            {"messages": [*history, HumanMessage(content=turn.question)]},
            config={
                "run_name": "chat_orchestrator",
                "tags": ["chat", "orchestrator"],
                "metadata": {"ad_id": turn.ad_id},
            },
        )
        last = final["messages"][-1]
        answer = last.content if isinstance(getattr(last, "content", None), str) else ""
        meta = final.get("tool_meta") or {
            "source": "orchestrator",
            "label": "CLIO",
            "engine": f"OpenAI · {model_name}",
        }
        return ChatAnswer(answer=answer, meta=meta)

    return _ask_full
