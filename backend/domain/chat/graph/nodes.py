# 슈퍼바이저 그래프 노드 팩토리 — load_context·supervisor·delegate·interrupt·execute·synthesize.
"""ChatGraphDeps 클로저로 노드를 생성한다. 각 노드: async def(state, config=None).

multi-step ReAct(연쇄 위임)는 deferred — v1은 단일 위임(1 turn)만 지원한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from langchain_core.messages import AIMessage
from langgraph.types import RunnableConfig, interrupt

from domain.chat.adapters.execution import execute_chat_action
from domain.chat.contracts.agent_io import ProposedAction, SubAgentRequest
from domain.chat.graph.supervisor import _last_user_text, decide_route

if TYPE_CHECKING:
    from domain.chat.contracts.ports import ChatRepo, MemoryStore, SubAgent

# 단일 위임 v1 안전망 — 다중 위임(ReAct) 구현 전까지 상한 도달 시 synthesize로 빠진다.
# TODO(다중위임): _after_delegate에 delegations >= _MAX_DELEGATIONS 초과 시
# synthesize로 분기 추가 — ReAct 도입 시 구현.
_MAX_DELEGATIONS = 4


@dataclass
class ChatGraphDeps:
    """그래프 빌더에 주입되는 의존성 묶음."""

    llm: object
    repo: ChatRepo | None
    memory: MemoryStore | None
    subagents: dict[str, SubAgent] = field(default_factory=dict)
    executor: object | None = None
    settings: object | None = None
    clio: object | None = None  # general 라우트용 CLIO callable — 없으면 결정론 폴백


def _card(pending: dict) -> dict:
    """승인 카드 요약 — interrupt 값으로 노출되는 최소 정보."""
    return {
        "tier": pending["tier"],
        "action_type": pending["action_type"],
        "target_campaign_id": pending.get("target_campaign_id"),
        "rationale": pending["rationale"],
    }


def _safe_stream_writer() -> object | None:
    """custom 스트림 writer — 구독 중이면 writer, 미구독/컨텍스트 밖이면 None."""
    try:
        from langgraph.config import get_stream_writer  # noqa: PLC0415

        return get_stream_writer()
    except Exception:  # noqa: BLE001
        return None


# 신원(org/user/project)을 서브에이전트로 넘기는 단일 결정론 통로 — LLM 산출과 무관하게 항상 주입.
# 인증 도입 시 orchestrator가 토큰 도출 org를 state에 실으면 자동 정렬(멀티테넌시 스펙).
def _scope_context_ids(state: dict) -> dict:
    """state 최상위 신원을 context_ids에 병합 — 서브에이전트 read 툴의 org 스코프 통로."""
    ctx = dict(state.get("context_ids") or {})
    for key in ("organization_id", "user_id", "project_id"):
        if state.get(key):
            ctx[key] = state[key]
    return ctx


async def _general_answer(clio, text: str, history: list, context: str | None = None) -> str:
    """CLIO general 답변 — 스트리밍 지원 시 토큰을 custom 스트림으로 흘리며 누적.

    context(플랫폼 맥락·기억)는 CLIO 시스템 프롬프트에 주입된다(컨시어지 인지).
    스트리밍 미지원(plain callable)이거나 custom 미구독이면 전체 호출로 폴백.
    실패 시 표시=영속 일치를 위해 흘린 조각이 있으면 그것을, 없으면 폴백 문구를 돌려준다.
    """
    stream_fn = getattr(clio, "stream", None)
    if stream_fn is not None:
        writer = _safe_stream_writer()
        if writer is not None:
            parts: list[str] = []
            try:
                async for piece in stream_fn(text, history, context):
                    parts.append(piece)
                    writer({"token": piece})
                return "".join(parts)
            except Exception:  # noqa: BLE001 — 부분 스트림이면 그대로, 아니면 전체 호출
                if parts:
                    return "".join(parts)
    try:
        return await clio(text, history, context)
    except Exception:  # noqa: BLE001 — CLIO 실패 시 결정론 폴백
        return "무엇을 도와드릴까요?"


class _Nodes:
    """의존성을 클로저로 바인딩한 노드 컨테이너."""

    def __init__(self, deps: ChatGraphDeps) -> None:
        self._d = deps

    # ── load_context ──────────────────────────────────────────────────────────
    async def load_context(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        deps = self._d
        session_id = (config or {}).get("configurable", {}).get("thread_id")
        short_term: list[dict] = []
        long_term: list[dict] = []

        if deps.repo and session_id:
            try:
                msgs = await deps.repo.get_messages(uuid.UUID(session_id), limit=20)
                short_term = [{"role": m.role, "content": m.content} for m in msgs]
            except Exception:  # noqa: BLE001 — DB 없으면 빈 리스트로 계속
                short_term = []

        if deps.memory:
            try:
                hits = await deps.memory.recall(
                    query=_last_user_text(state["messages"]),
                    project_id=state.get("project_id"),
                    user_id=state.get("user_id"),
                    k=5,
                    salience_floor=0.9,
                )
                long_term = [h.content for h in hits]
            except Exception:  # noqa: BLE001
                long_term = []

        return {
            "short_term": short_term,
            "long_term": long_term,
            "pending_action": None,
            "route": "",
        }

    # ── supervisor ───────────────────────────────────────────────────────────
    async def supervisor(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        route = await decide_route(state["messages"], self._d.llm)
        return {"route": route.value}

    # ── delegate ─────────────────────────────────────────────────────────────
    async def delegate(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        deps = self._d
        route = state["route"]
        sub = deps.subagents.get(route)
        delegations = state.get("delegations", 0) + 1

        if sub is None:
            return {
                "sub_results": [{"route": route, "error": "no subagent"}],
                "delegations": delegations,
            }

        req = SubAgentRequest(
            question=_last_user_text(state["messages"]),
            context_ids=_scope_context_ids(state),
            knobs=(state.get("context_ids") or {}).get("knobs", {}),
        )
        result = await sub.run(req)
        update: dict = {
            "sub_results": [result.model_dump()],
            "citations": [c.model_dump() for c in result.citations],
            "delegations": delegations,
        }

        if result.proposed_action and result.proposed_action.requires_approval:
            update["pending_action"] = result.proposed_action.model_dump()

        return update

    # ── interrupt_node ────────────────────────────────────────────────────────
    async def interrupt_node(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        # interrupt()는 반드시 첫 문장 — LangGraph가 이 지점에서 그래프를 멈추고
        # resume 값을 이 함수의 반환값으로 주입한다(두 번째 ainvoke 시).
        decision = interrupt({"approval_request": _card(state["pending_action"])})
        return {"approval_decision": decision}

    # ── execute ───────────────────────────────────────────────────────────────
    async def execute(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        deps = self._d
        pa_dict = state["pending_action"]
        decision = state.get("approval_decision") or {}
        pa = ProposedAction(**pa_dict)

        from domain.management.wiring import resolve_execution_mode  # noqa: PLC0415

        mode = resolve_execution_mode(deps.settings)
        try:
            result = await execute_chat_action(
                pa,
                tenant_id=str(state.get("organization_id") or "org_demo"),
                approver_id=str(decision.get("approver_id") or "user"),
                executor=deps.executor,
                execution_mode=mode,
            )
            return {
                "execution_result": (
                    result.model_dump(mode="json") if result is not None else {"deferred": True}
                )
            }
        except Exception as e:  # noqa: BLE001
            return {"execution_result": {"error": str(e)}}

    # ── synthesize ────────────────────────────────────────────────────────────
    async def synthesize(self, state: dict, config: Optional[RunnableConfig] = None) -> dict:  # noqa: UP045
        from domain.chat.contracts.agent_io import Route  # noqa: PLC0415

        sub_results: list[dict] = state.get("sub_results") or []
        execution_result: dict | None = state.get("execution_result")
        deps = self._d

        # general 라우트 + CLIO 주입됨 + 서브에이전트 답변 없음 → CLIO 호출(스트리밍 우선)
        if state.get("route") == Route.GENERAL.value and deps.clio is not None and not sub_results:
            from domain.chat.adapters.platform_context import build_general_context  # noqa: PLC0415

            answer = await _general_answer(
                deps.clio,
                _last_user_text(state["messages"]),
                state.get("short_term") or [],
                build_general_context(state.get("long_term")),
            )
        elif sub_results:
            # 서브에이전트 답변(management/simulation/generation 라우트)
            answer = sub_results[-1].get("answer") or "결과를 가져왔습니다."
        else:
            # general + CLIO 없음 — 결정론 폴백
            answer = "무엇을 도와드릴까요?"

        # 집행 결과 한 줄 추가
        if execution_result:
            if "error" in execution_result:
                answer += f"\n집행 실패: {execution_result['error']}"
            elif execution_result.get("deferred"):
                answer += "\n매니지먼트 화면에서 완료하세요."
            else:
                answer += "\n집행 완료."

        return {
            "final_answer": answer,
            "messages": [AIMessage(content=answer)],
        }


def make_nodes(deps: ChatGraphDeps) -> _Nodes:
    """ChatGraphDeps → 바인딩된 노드 컨테이너 반환."""
    return _Nodes(deps)
