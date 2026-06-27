# 공통 오케스트레이터 Deep Agent — LangGraph 3노드 루프 (act-first, MAX_ITER=3)
"""단일 패스 Orchestrator를 대체하는 Deep Agent.

act-first 전략: 첫 이터레이션에 management 질문이면 즉시 호출하고, 결과 보고 최종 답 합성.
루프 상한(MAX_ITER=3)으로 비용 통제. requires_approval=True면 즉시 합성(재호출 없음).

반환 인터페이스: SubagentResult (기존 Orchestrator 계약과 동일).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from api.assistant.contracts import Action, SubagentRequest, SubagentResult
from api.assistant.registry import Handler
from core.schemas import ChatMessage

logger = logging.getLogger("clickme")

MAX_ITER = 3

_SYS_ORCHESTRATOR = """\
당신은 ClickMe 광고 플랫폼의 오케스트레이터 AI입니다.
도구(ask_management, ask_generator)를 호출해 정보를 수집한 뒤, 한국어로 최종 답변을 작성합니다.

규칙:
- 광고 운영·성과·예산·정책 질문 → ask_management 호출
- 광고 시안·카피 생성 요청 → ask_generator 호출
- 이미 충분한 정보가 있으면 추가 호출 없이 답합니다
- 최종 답변에 수치·근거가 있으면 도구 결과에서 그대로 인용합니다
"""

# 도구 스펙 정의 (LLM function-calling)
_TOOL_SPECS = [
    {
        "name": "ask_management",
        "description": (
            "캠페인 현황·성과·예산·이상·KPI·벤치마크·정책 관련 질문."
            " 실측 데이터와 KB 정책 근거를 제공한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "질문 내용"},
                "campaign_id": {
                    "type": "string",
                    "description": "특정 캠페인 ID (선택)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_generator",
        "description": (
            "광고 시안·카피·이미지 생성 요청."
            " management_context로 성과 기반 개선 컨텍스트를 전달할 수 있다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "생성 요청 내용"},
                "management_context": {
                    "type": "string",
                    "description": "매니지먼트 결과(성과·제약 맥락) (선택)",
                },
            },
            "required": ["query"],
        },
    },
]


class _OState(TypedDict):
    """오케스트레이터 내부 상태."""

    messages: Annotated[list, add_messages]
    orig_messages: list  # 핸들러에 전달할 원본 ChatMessage (변경 안 됨)
    sub_results: dict[str, Any]
    iteration: int
    thread_id: str | None
    requires_approval: bool
    session_id: str
    context_ad_id: str | None


def _chat_to_lc(m: ChatMessage) -> HumanMessage | AIMessage:
    """ChatMessage → LangChain message 객체."""
    if m.role == "user":
        return HumanMessage(content=m.content)
    return AIMessage(content=m.content)


def _sub_to_text(result: SubagentResult) -> str:
    """SubagentResult → 도구 응답 텍스트 (LLM이 읽을 수 있도록 직렬화)."""
    meta = result.meta or {}
    lines = [result.message]
    if meta.get("citations"):
        refs = "; ".join(
            f"{c.get('title', '?')}({c.get('source', '?')})" for c in meta["citations"][:3]
        )
        lines.append(f"[인용: {refs}]")
    if meta.get("requires_approval"):
        lines.append("[HITL: 사람 승인 필요]")
    return "\n".join(lines)


def build_deep_agent_graph(
    llm,
    management_handler: Handler | None = None,
    generator_handler: Handler | None = None,
    checkpointer=None,
) -> Callable[[SubagentRequest], Awaitable[SubagentResult]]:
    """Deep Agent 팩토리 — graph를 빌드하고 run(SubagentRequest) → SubagentResult를 반환.

    management_handler / generator_handler가 None이면 mock 핸들러로 대체.
    실 구현이 들어오면 wiring.py에서 실 핸들러를 주입해 교체.
    checkpointer가 None이면 MemorySaver(인메모리). wiring이 PG 싱글턴을 주입하면 영속·멀티턴.
    """
    _mgt_handler = management_handler or _mock_management
    _gen_handler = generator_handler or _mock_generator

    # ── LLM 준비 (function calling 바인딩) ──────────────────────────────────
    llm_with_tools = llm.bind_tools(_TOOL_SPECS)
    llm_plain = llm  # MAX_ITER 도달 시 도구 없이 최종 답 생성

    # ── 노드 정의 ────────────────────────────────────────────────────────────

    async def orchestrate(state: _OState) -> dict:
        """LLM이 도구 호출 여부를 결정하는 노드."""
        if state["iteration"] >= MAX_ITER or state["requires_approval"]:
            # 더 이상 도구 호출 없이 최종 합성
            resp = await llm_plain.ainvoke(state["messages"])
            return {"messages": [resp], "iteration": state["iteration"] + 1}

        # act-first: 첫 이터레이션에서 management 키워드 감지 시 즉시 힌트
        messages = list(state["messages"])
        if state["iteration"] == 0 and not state["sub_results"]:
            # 시스템 힌트: 첫 이터레이션에서 도구 선택을 유도
            messages = [
                SystemMessage(
                    content=_SYS_ORCHESTRATOR + "\n첫 응답에서 적합한 도구를 즉시 호출하세요."
                ),
                *messages,
            ]

        resp = await llm_with_tools.ainvoke(messages)
        return {"messages": [resp], "iteration": state["iteration"] + 1}

    async def dispatch(state: _OState) -> dict:
        """tool_calls를 실행해 sub_results에 저장하고 ToolMessage를 반환하는 노드."""
        last = state["messages"][-1]
        tool_calls = getattr(last, "tool_calls", [])

        tool_msgs: list[ToolMessage] = []
        new_sub = dict(state["sub_results"])
        new_thread_id = state["thread_id"]
        new_requires = state["requires_approval"]

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("args", {})
            tool_id = tc.get("id", name)

            try:
                if name == "ask_management":
                    req = SubagentRequest(
                        messages=state["orig_messages"],
                        session_id=state["session_id"],
                        context_ad_id=args.get("campaign_id") or state["context_ad_id"],
                    )
                    result: SubagentResult = await _mgt_handler(req)
                    new_sub["management"] = result.meta
                    if result.meta.get("thread_id"):
                        new_thread_id = result.meta["thread_id"]
                    if result.meta.get("requires_approval"):
                        new_requires = True

                elif name == "ask_generator":
                    mgt_ctx = args.get("management_context") or (
                        new_sub.get("management", {}).get("summary", "")
                    )
                    req = SubagentRequest(
                        messages=state["orig_messages"],
                        session_id=state["session_id"],
                    )
                    if mgt_ctx:
                        req.improve_context = {"summary": mgt_ctx}
                    result = await _gen_handler(req)
                    new_sub["generator"] = result.meta
                    # ASK/TRIGGER → 즉시 END (되묻기/트리거는 루프 없이 전달)
                    if result.action in (Action.ASK, Action.TRIGGER):
                        tool_msgs.append(
                            ToolMessage(
                                content=_sub_to_text(result),
                                tool_call_id=tool_id,
                            )
                        )
                        return {
                            "messages": tool_msgs,
                            "sub_results": new_sub,
                            "thread_id": new_thread_id,
                            "requires_approval": new_requires,
                        }
                else:
                    result = SubagentResult(
                        action=Action.ANSWER,
                        message=f"[알 수 없는 도구: {name}]",
                    )

                tool_msgs.append(ToolMessage(content=_sub_to_text(result), tool_call_id=tool_id))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[deep_agent] %s 실패: %s", name, exc)
                tool_msgs.append(ToolMessage(content=f"[{name} 오류: {exc}]", tool_call_id=tool_id))

        return {
            "messages": tool_msgs,
            "sub_results": new_sub,
            "thread_id": new_thread_id,
            "requires_approval": new_requires,
        }

    def route(state: _OState) -> str:
        """tool_calls가 있으면 dispatch, 없으면 END."""
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "dispatch"
        return END

    # ── 그래프 빌드 ──────────────────────────────────────────────────────────
    builder = StateGraph(_OState)
    builder.add_node("orchestrate", orchestrate)
    builder.add_node("dispatch", dispatch)
    builder.add_edge(START, "orchestrate")
    builder.add_conditional_edges("orchestrate", route, {"dispatch": "dispatch", END: END})
    builder.add_edge("dispatch", "orchestrate")

    # 외부 주입(PG 싱글턴) 우선, 없으면 인메모리 폴백(Windows 로컬·테스트).
    graph = builder.compile(checkpointer=checkpointer or MemorySaver())

    # ── 공개 인터페이스 ───────────────────────────────────────────────────────

    async def run(req: SubagentRequest) -> SubagentResult:
        """SubagentRequest → SubagentResult (기존 Orchestrator 계약 유지)."""
        lc_messages = [_chat_to_lc(m) for m in req.messages]

        initial: _OState = {
            "messages": lc_messages,
            "orig_messages": req.messages,
            "sub_results": {},
            "iteration": 0,
            "thread_id": None,
            "requires_approval": False,
            "session_id": req.session_id or "",
            "context_ad_id": req.context_ad_id,
        }

        config = {
            "run_name": "deep-agent-turn",
            "tags": ["deep-agent", "orchestrator", "management"],
            "metadata": {
                "session_id": req.session_id,
                "iteration_budget": MAX_ITER,
            },
            "configurable": {"thread_id": req.session_id or "default"},
        }

        final: _OState = await graph.ainvoke(initial, config=config)
        return _state_to_result(final)

    return run


def _state_to_result(state: _OState) -> SubagentResult:
    """최종 state → SubagentResult 변환."""
    # 마지막 AI 메시지에서 최종 텍스트 추출
    final_text = ""
    for msg in reversed(state["messages"]):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            final_text = msg.content if isinstance(msg.content, str) else str(msg.content)
            break

    # management sub_result에서 meta 재구성
    mgt_meta = state["sub_results"].get("management", {})
    gen_meta = state["sub_results"].get("generator", {})
    # 호출된 서브에이전트 중 주 소스를 source로 — frontend가 source로 분기하므로 유지
    primary_source = (
        mgt_meta.get("source", "management")
        if mgt_meta
        else gen_meta.get("source", "generator")
        if gen_meta
        else "deep-agent"
    )
    combined_meta: dict = {
        "source": primary_source,
        "label": mgt_meta.get("label", gen_meta.get("label", "오케스트레이터")),
        "engine": mgt_meta.get("engine", gen_meta.get("engine", "Deep Agent")),
        "citations": mgt_meta.get("citations", []) + gen_meta.get("citations", []),
        "used_tools": (
            mgt_meta.get("used_tools", [])
            + (["ask_management"] if mgt_meta else [])
            + (["ask_generator"] if gen_meta else [])
        ),
        "requires_approval": state["requires_approval"],
        "thread_id": state["thread_id"],
        # G2 — suggested_action/evidence/campaigns 캐리. 누락 시 RESULT/REVIEW/ACTIONBAR
        # 카드가 영영 안 뜨고(chat.py compose_turn 입력 부재), record_turn·메모리 노트도 빈값.
        "suggested_action": mgt_meta.get("suggested_action"),
        "evidence": mgt_meta.get("evidence", {}),
        "campaigns": mgt_meta.get("campaigns", []),
        "sub_results": {
            "management": _compact_meta(mgt_meta),
            "generator": _compact_meta(gen_meta),
        },
    }

    return SubagentResult(
        action=Action.ANSWER,
        message=final_text,
        meta=combined_meta,
    )


def _compact_meta(meta: dict) -> dict | None:
    if not meta:
        return None
    return {k: v for k, v in meta.items() if k in ("source", "label", "engine", "citations")}


# ── Mock 핸들러 (실 구현 전까지 wiring.py에서 주입) ───────────────────────────


async def _mock_management(req: SubagentRequest) -> SubagentResult:
    """management 실 구현 전 mock — wiring.py에서 실 핸들러로 교체."""
    return SubagentResult(
        action=Action.ANSWER,
        message=f"[MOCK-MGT] 매니지먼트 응답 (query={req.last_user_text[:40]}...)",
        meta={"source": "management", "citations": [], "used_tools": ["mock"]},
    )


async def _mock_generator(req: SubagentRequest) -> SubagentResult:
    """generator 실 구현 전 mock — wiring.py에서 실 핸들러로 교체."""
    return SubagentResult(
        action=Action.ANSWER,
        message=f"[MOCK-GEN] 광고 시안 생성 완료 (query={req.last_user_text[:40]}...)",
        meta={"source": "generator", "citations": [], "used_tools": ["mock"]},
    )


# ── 공개 심볼 ────────────────────────────────────────────────────────────────
__all__ = ["build_deep_agent_graph", "MAX_ITER", "_mock_management", "_mock_generator"]
