# 생성 서브에이전트 ReAct — 자연어 질문을 read 툴(gen_detail/gen_list)+KB로 답한다.
"""build_generator_agent(settings) → async answer 콜러블, 또는 None(폴백 신호).

sim_agent 패턴 복제(읽기 전용). 생성물 수치·목록은 gen 툴, 사용법·흐름은 search_kb(platform_guide).
새 시안 생성(트리거)은 여기서 하지 않는다 — 호출부가 별도 경로로 처리한다.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_ROUNDS = 4
_GEN_KB_TYPES = ["platform_guide"]

_SYSTEM = (
    "너는 ClickMe 광고 생성 어시스턴트다. 한국어로 간결하게 답한다.\n"
    "도구로 근거를 모은 뒤 답하라.\n"
    "- 생성 결과·후보·QA·목록은 gen_detail/gen_list로 조회해 그 값만 인용한다.\n"
    "- 생성 사용법·흐름·페이지는 search_kb로 설명한다.\n"
    "- 새 시안 생성(트리거)은 여기서 하지 않는다. 근거가 없으면 모른다고 답한다.\n"
    "문장 끝에 콜론을 쓰지 말 것."
)


def build_generator_agent(settings) -> Any:
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

    from domain.chat.adapters import gen_tools  # noqa: PLC0415
    from domain.chat.wiring import build_embedding_provider  # noqa: PLC0415
    from domain.management.assistant.retriever import KbRetriever  # noqa: PLC0415

    retriever = KbRetriever(embedder=build_embedding_provider(settings))
    llm = init_chat_model(
        settings.chat_orchestrator_model,
        model_provider=settings.chat_orchestrator_provider,
        temperature=0,
    )

    class _State(MessagesState, total=False):
        generation_id: str | None
        organization_id: str | None  # 서버 결정론 스코프(LLM 산출 무시) — 테넌트 격리
        used_tools: list[str]
        kb_citations: list[dict]
        gen_data: dict
        tool_rounds: int

    @tool
    async def gen_detail(generation_id: str | None = None, org_id: str | None = None) -> dict:
        """특정 생성 작업의 상세(상태·후보 수·QA 통과·선택안)를 조회한다."""
        if not generation_id:
            return {"error": "need_generation_id"}
        return await gen_tools.gen_detail(generation_id, org_id=org_id)

    @tool
    async def gen_list(limit: int = 10, org_id: str | None = None) -> dict:
        """최근 생성 작업 목록(generation_id·상태·상품명)을 조회한다."""
        return await gen_tools.gen_list(limit=limit, org_id=org_id)

    @tool
    async def search_kb(query: str) -> list[dict]:
        """광고 생성 사용법·흐름·페이지 등 플랫폼 가이드를 검색한다."""
        try:
            return await retriever.search(query, k=4, source_types=_GEN_KB_TYPES)
        except Exception:  # noqa: BLE001 — KB 미적재면 빈 결과로 진행
            return []

    tools = [gen_detail, gen_list, search_kb]
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
        gen_data = dict(state.get("gen_data", {}))
        ctx_id = state.get("generation_id")
        org_id = state.get("organization_id")
        out: list[ToolMessage] = []
        for call in ai.tool_calls:
            name, args, cid = call["name"], dict(call.get("args", {})), call["id"]
            if name == "gen_detail" and not args.get("generation_id"):
                args["generation_id"] = ctx_id
            # org 스코프는 서버가 결정론 주입(LLM 산출 무시) — 테넌트 격리.
            if name in ("gen_detail", "gen_list"):
                args["org_id"] = org_id
            result = await by_name[name].ainvoke(args)
            if name not in used:
                used.append(name)
            if name == "search_kb":
                kb.extend(result if isinstance(result, list) else [])
            elif name == "gen_detail" and isinstance(result, dict) and "error" not in result:
                gen_data = result
            out.append(
                ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=cid)
            )
        return {
            "messages": out,
            "used_tools": used,
            "kb_citations": kb,
            "gen_data": gen_data,
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    def route(state: _State) -> str:
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
                "generation_id": (context_ids or {}).get("generation_id"),
                "organization_id": (context_ids or {}).get("organization_id"),
            },
            config={"run_name": "generator_subagent", "tags": ["chat", "generation"]},
        )
        last = final["messages"][-1] if final.get("messages") else None
        return {
            "answer": last.content if isinstance(getattr(last, "content", None), str) else "",
            "used_tools": list(final.get("used_tools", [])),
            "kb_citations": list(final.get("kb_citations", [])),
            "gen_data": final.get("gen_data", {}),
        }

    return answer
