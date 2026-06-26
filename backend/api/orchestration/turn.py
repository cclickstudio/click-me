# 오케스트레이션 턴 그래프 — plan·execute 노드를 LangGraph로 묶어 트레이스·STM·HITL 토대를 만든다
from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from api.orchestration.executor import execute_plan
from api.orchestration.planner import build_plan
from api.orchestration.registry import AgentRegistry


class TurnState(TypedDict, total=False):
    route: Any
    req: Any
    plan: Any
    result: Any


def build_orchestrator_graph(registry: AgentRegistry):
    # registry를 노드 클로저에 바인딩 — 그래프는 한 번 빌드해 재사용(호출자가 캐시).
    async def plan_node(state: TurnState) -> dict:
        # req.question 직접 접근 — 폴백 없음(req가 비정상이면 AttributeError로 fail-loud).
        return {"plan": build_plan(state["route"], query=state["req"].question)}

    async def execute_node(state: TurnState) -> dict:
        return {"result": await execute_plan(state["plan"], req=state["req"], registry=registry)}

    g = StateGraph(TurnState)
    g.add_node("plan", plan_node)
    g.add_node("execute", execute_node)
    g.add_edge(START, "plan")
    g.add_edge("plan", "execute")
    g.add_edge("execute", END)
    # S1: stateless(checkpointer 없음). STM 체크포인터는 M 슬라이스에서 compile 인자로 추가.
    return g.compile()


async def run_turn(graph, route: Any, *, req: Any) -> Any:
    # 루트 트레이스 — 노드(plan·execute)가 assistant.chat.turn 아래 자식 run으로 중첩된다.
    final = await graph.ainvoke(
        {"route": route, "req": req},
        config={"run_name": "assistant.chat.turn", "tags": ["assistant"]},
    )
    return final["result"]
