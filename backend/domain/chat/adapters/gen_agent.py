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
    "- '이름(상품명) X인 생성물'은 gen_find_by_name(X)로 찾아 단건이면 gen_detail로 상세, "
    "다건이면 나열, 없으면 '없음'으로 답한다.\n"
    "- 생성 사용법·흐름·페이지는 search_kb로 설명한다.\n"
    "- 사용자가 '새 시안/광고 만들어/생성해'를 원하면 start_generation으로 실행한다.\n"
    "  실행 전 상품명·설명·타깃·목표를 확인하라(상품명은 필수). 값을 주거나 동의하면 실행하고 "
    "사용한 설정을 답에 명시한다.\n"
    "- 근거가 없으면 모른다고 답한다. 문장 끝에 콜론을 쓰지 말 것."
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
        api_key=settings.anthropic_api_key,  # os.environ 의존 제거 — 키를 명시 전달
        temperature=0,
    )

    class _State(MessagesState, total=False):
        generation_id: str | None
        organization_id: str | None  # 서버 결정론 스코프(LLM 산출 무시) — 테넌트 격리
        project_id: str | None  # 트리거 대상 프로젝트 — 서버 주입
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
    async def gen_find_by_name(name: str, org_id: str | None = None, limit: int = 10) -> dict:
        """상품명으로 생성물을 부분일치 검색해 후보 목록(generation_id 포함)을 반환한다."""
        return await gen_tools.gen_find_by_name(name=name, org_id=org_id, limit=limit)

    @tool
    async def search_kb(query: str) -> list[dict]:
        """광고 생성 사용법·흐름·페이지 등 플랫폼 가이드를 검색한다."""
        try:
            return await retriever.search(query, k=4, source_types=_GEN_KB_TYPES)
        except Exception:  # noqa: BLE001 — KB 미적재면 빈 결과로 진행
            return []

    @tool
    async def start_generation(
        product_name: str,
        product_description: str = "",
        target_audience: str = "",
        campaign_objective: str = "conversion",
        project_id: str | None = None,
    ) -> dict:
        """새 광고 시안 생성을 실제로 실행(비동기)한다. 상품명 필수.

        실행 전 상품명·설명·타깃·목표를 사용자에게 확인하라. project_id는 서버가 주입한다.
        """
        if not product_name or not product_name.strip():
            return {"error": "need_product", "message": "상품명을 알려주세요."}
        from pydantic import ValidationError  # noqa: PLC0415

        from domain.generator.contracts.enums import GenerationMode  # noqa: PLC0415
        from domain.generator.contracts.schemas import GenerationCreateRequest  # noqa: PLC0415
        from domain.generator.service.generator_service import (  # noqa: PLC0415
            start_generation as _start_gen,
        )

        try:
            gen_req = GenerationCreateRequest(
                mode=GenerationMode.CREATE,
                product_name=product_name,
                product_description=product_description,
                target_audience=target_audience,
                campaign_objective=campaign_objective or "conversion",
                project_id=project_id,
            )
        except ValidationError as exc:
            return {"error": "invalid", "detail": exc.errors()[0].get("msg", "")}
        gid = await _start_gen(gen_req, created_by=None)
        return {"generation_id": gid, "product_name": product_name}

    tools = [gen_detail, gen_list, gen_find_by_name, search_kb, start_generation]
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
            if name in ("gen_detail", "gen_list", "gen_find_by_name"):
                args["org_id"] = org_id
            # 트리거: project는 서버가 컨텍스트에서 주입(LLM은 상품 정보만 채움).
            if name == "start_generation":
                args["project_id"] = state.get("project_id")
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
                "generation_id": (context_ids or {}).get("generation_id"),
                "organization_id": (context_ids or {}).get("organization_id"),
                "project_id": (context_ids or {}).get("project_id"),
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
