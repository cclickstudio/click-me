# 슈퍼바이저 그래프 빌더 — StateGraph 조립 + 조건부 엣지 배선.
"""build_chat_graph(deps, *, checkpointer) → CompiledGraph.

그래프 형태:
    START → load_context → supervisor
    supervisor ─(route==general)→ synthesize
               ─(else)──────────→ delegate
    delegate ─(pending_action 있음)→ interrupt_node
             ─(else)──────────────→ synthesize
    interrupt_node ─(approved)→ execute → synthesize
                   ─(else)──────────────→ synthesize
    synthesize → END

multi-step ReAct(연쇄 위임)는 deferred — v1은 단일 위임만 지원한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

from domain.chat.contracts.agent_io import Route
from domain.chat.graph.nodes import ChatGraphDeps, make_nodes
from domain.chat.graph.state import ChatState

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver

# re-export — 외부 소비자가 builder에서만 import할 수 있도록.
__all__ = ["ChatGraphDeps", "build_chat_graph"]


# ── 조건부 엣지 라우터 ────────────────────────────────────────────────────────


def _after_supervisor(state: dict) -> str:
    return "synthesize" if state.get("route") == Route.GENERAL.value else "delegate"


def _after_delegate(state: dict) -> str:
    return "interrupt_node" if state.get("pending_action") else "synthesize"


def _after_interrupt(state: dict) -> str:
    return "execute" if (state.get("approval_decision") or {}).get("approved") else "synthesize"


# ── 빌더 ──────────────────────────────────────────────────────────────────────


def build_chat_graph(deps: ChatGraphDeps, *, checkpointer: BaseCheckpointSaver):
    """그래프 컴파일 — 노드는 deps 클로저로 바인딩, checkpointer는 HITL interrupt/resume에 필요."""
    n = make_nodes(deps)

    g = StateGraph(ChatState)
    g.add_node("load_context", n.load_context)
    g.add_node("supervisor", n.supervisor)
    g.add_node("delegate", n.delegate)
    g.add_node("interrupt_node", n.interrupt_node)
    g.add_node("execute", n.execute)
    g.add_node("synthesize", n.synthesize)

    g.add_edge(START, "load_context")
    g.add_edge("load_context", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        _after_supervisor,
        {"delegate": "delegate", "synthesize": "synthesize"},
    )
    g.add_conditional_edges(
        "delegate",
        _after_delegate,
        {"interrupt_node": "interrupt_node", "synthesize": "synthesize"},
    )
    g.add_conditional_edges(
        "interrupt_node",
        _after_interrupt,
        {"execute": "execute", "synthesize": "synthesize"},
    )
    g.add_edge("execute", "synthesize")
    g.add_edge("synthesize", END)

    return g.compile(checkpointer=checkpointer)
