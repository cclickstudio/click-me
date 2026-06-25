# 시뮬 서브에이전트 ReAct — 자연어 질문을 read 툴(sim_result/sim_persona_basis)+KB로 답한다.
"""build_simulation_agent(settings) → async answer 콜러블, 또는 None(폴백 신호).

매니지먼트 어시스턴트(assistant/graph.py) 패턴을 읽기 전용으로 축약(propose_action·HITL 없음).
숫자·신뢰지표는 sim 툴(DB 실측)에서만, 데이터 출처·방법론은 search_kb로(환각 방지).
키 없음/use_mock이면 None을 반환 — 호출부(simulation_subagent)가 구조화 폴백으로 처리.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_ROUNDS = 4
# 시뮬 서브에이전트 검색 KB 네임스페이스 — 방법론·신뢰지표 + KOBACO·근거(제공 시).
_SIM_KB_TYPES = ["persona_methodology", "simulation_trust", "kobaco_baseline", "evidence"]

_SYSTEM = (
    "너는 ClickMe 광고 시뮬레이터 애널리스트다. 한국어로 간결하게 답한다.\n"
    "도구로 근거를 모은 뒤 답하라.\n"
    "- 시뮬 수치·신뢰지표(클릭의향률·신뢰구간·effective_n·QA 통과수·구매의도·신뢰도·거부율)는 "
    "sim_result로 조회해 그 값만 인용한다. 추정·환각 금지.\n"
    "- '무슨 데이터로 페르소나를 만들었나'는 sim_persona_basis(표본 분포)와 "
    "search_kb(데이터 출처·생성 방법)로 답한다.\n"
    "- '현재 시뮬레이션 현황'·'내 시뮬 목록/개수'는 sim_list로 조회한다(조직 전체).\n"
    "- '이름이 X인 시뮬레이션'은 sim_find_by_name(X)로 후보를 찾고, 단건이면 그 simulation_id로 "
    "sim_result/sim_persona_basis로 상세를 답한다. 다건이면 후보를 나열하고, 없으면 "
    "'없음'으로 답한다.\n"
    "- '신뢰할 수 있나'는 신뢰구간·effective_n·QA·variance_warning을 근거로 설명하고, "
    "방향성은 신뢰 가능하나 절대값 단언은 피한다고 안내한다.\n"
    "- 예측(상대)과 실측(절대)을 수치로 환산하지 말 것. 근거 없으면 모른다고 답한다.\n"
    "문장 끝에 콜론을 쓰지 말 것."
)


def build_simulation_agent(settings) -> Any:
    """async answer(question, context_ids)->dict 또는 None(폴백 신호). 키/실모드일 때만 ReAct."""
    if getattr(settings, "use_mock", True) or not getattr(settings, "anthropic_api_key", None):
        return None

    from langchain.chat_models import init_chat_model  # noqa: PLC0415
    from langchain_core.messages import (  # noqa: PLC0415
        AIMessage,
        HumanMessage,
        SystemMessage,
        ToolMessage,
    )
    from langchain_core.tools import tool  # noqa: PLC0415
    from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: PLC0415

    from domain.chat.adapters import sim_tools  # noqa: PLC0415
    from domain.chat.wiring import build_embedding_provider  # noqa: PLC0415
    from domain.management.assistant.retriever import KbRetriever  # noqa: PLC0415

    retriever = KbRetriever(embedder=build_embedding_provider(settings))
    llm = init_chat_model(
        settings.chat_orchestrator_model,
        model_provider=settings.chat_orchestrator_provider,
        api_key=settings.anthropic_api_key,  # os.environ 의존 제거 — 키를 명시 전달
        temperature=0,
    )

    class _State(MessagesState, total=False):
        simulation_id: str | None
        organization_id: str | None  # 서버 결정론 스코프(LLM 산출 무시) — 테넌트 격리
        used_tools: list[str]
        kb_citations: list[dict]
        sim_data: dict
        tool_rounds: int

    @tool
    async def sim_result(simulation_id: str | None = None) -> dict:
        """시뮬레이션의 4대 KPI와 신뢰지표(신뢰구간·effective_n·QA·variance)를 조회한다."""
        if not simulation_id:
            return {"error": "need_simulation_id"}
        return await sim_tools.sim_result(simulation_id)

    @tool
    async def sim_persona_basis(simulation_id: str | None = None) -> dict:
        """시뮬에 쓰인 페르소나 표본의 분포(연령대·성별·지역·OCEAN 평균)를 조회한다."""
        if not simulation_id:
            return {"error": "need_simulation_id"}
        return await sim_tools.sim_persona_basis(simulation_id)

    @tool
    async def sim_list(
        limit: int = 10, org_id: str | None = None, status: str | None = None
    ) -> dict:
        """내 조직 시뮬레이션 현황 목록(시뮬ID·광고제목·상태·완료 시 KPI)을 조회한다."""
        return await sim_tools.sim_list(limit=limit, org_id=org_id, status=status)

    @tool
    async def sim_find_by_name(name: str, org_id: str | None = None, limit: int = 10) -> dict:
        """광고 제목으로 시뮬레이션을 부분일치 검색해 후보 목록(시뮬ID 포함)을 반환한다."""
        return await sim_tools.sim_find_by_name(name=name, org_id=org_id, limit=limit)

    @tool
    async def search_kb(query: str) -> list[dict]:
        """페르소나 데이터 출처·생성 방법론·신뢰 지표 정의 등 지식베이스를 검색한다."""
        try:
            return await retriever.search(query, k=4, source_types=_SIM_KB_TYPES)
        except Exception:  # noqa: BLE001 — KB 미적재면 빈 결과로 진행
            return []

    tools = [sim_result, sim_persona_basis, sim_list, sim_find_by_name, search_kb]
    bound = llm.bind_tools(tools)
    by_name = {t.name: t for t in tools}

    async def agent(state: _State) -> dict:
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=_SYSTEM), *msgs]
        model = bound if state.get("tool_rounds", 0) < _MAX_ROUNDS else llm
        return {"messages": [await model.ainvoke(msgs)]}

    async def tools_node(state: _State) -> dict:
        ai = state["messages"][-1]
        used = list(state.get("used_tools", []))
        kb = list(state.get("kb_citations", []))
        sim_data = dict(state.get("sim_data", {}))
        ctx_id = state.get("simulation_id")
        org_id = state.get("organization_id")
        out: list[ToolMessage] = []
        for call in ai.tool_calls:
            name, args, cid = call["name"], dict(call.get("args", {})), call["id"]
            # 컨텍스트 simulation_id 주입 — LLM이 생략하면 턴 컨텍스트 값을 쓴다.
            if name in ("sim_result", "sim_persona_basis") and not args.get("simulation_id"):
                args["simulation_id"] = ctx_id
            # org 스코프는 서버가 결정론 주입(LLM 산출 무시) — 테넌트 격리.
            if name in ("sim_list", "sim_find_by_name"):
                args["org_id"] = org_id
            result = await by_name[name].ainvoke(args)
            if name not in used:
                used.append(name)
            if name == "search_kb":
                kb.extend(result if isinstance(result, list) else [])
            elif name == "sim_result" and isinstance(result, dict) and "error" not in result:
                sim_data = result
            out.append(
                ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=cid)
            )
        return {
            "messages": out,
            "used_tools": used,
            "kb_citations": kb,
            "sim_data": sim_data,
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    def route(
        state: dict,
    ) -> str:  # _State(로컬 클래스) 주석 금지 — langgraph get_type_hints NameError
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    g = StateGraph(_State)
    g.add_node("agent", agent)
    g.add_node("tools", tools_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    graph = g.compile()

    async def answer(question: str, context_ids: dict | None) -> dict:
        final = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=question)],
                "simulation_id": (context_ids or {}).get("simulation_id"),
                "organization_id": (context_ids or {}).get("organization_id"),
            },
            config={"run_name": "simulation_subagent", "tags": ["chat", "simulation"]},
        )
        last = final["messages"][-1] if final.get("messages") else None
        return {
            "answer": last.content if isinstance(getattr(last, "content", None), str) else "",
            "used_tools": list(final.get("used_tools", [])),
            "kb_citations": list(final.get("kb_citations", [])),
            "sim_data": final.get("sim_data", {}),
        }

    return answer
