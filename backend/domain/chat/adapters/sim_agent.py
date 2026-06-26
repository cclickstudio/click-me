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
    "- '방금/최근/마지막 시뮬 결과'는 sim_list로 최신 시뮬을 찾아 그 simulation_id로 sim_result로 "
    "답한다. 방금 시작한 시뮬은 완료 전엔 목록에 없을 수 있다고 안내한다.\n"
    "- '이름이 X인 시뮬레이션'은 sim_find_by_name(X)로 후보를 찾고, 단건이면 그 simulation_id로 "
    "sim_result/sim_persona_basis로 상세를 답한다. 다건이면 후보를 나열하고, 없으면 "
    "'없음'으로 답한다.\n"
    "- [현재 맥락]에 '첨부된 광고 있음'이 보이고 사용자가 시뮬 '실행/돌려'를 원할 때, "
    "표본·타깃·제목·설명이 이번 메시지·[이전 대화]에 없고 아직 묻지 않았으면 start_simulation을 "
    "호출하지 말고 '표본 몇 명으로, 어떤 타깃(연령·성별)으로 돌릴까요? (기본 표본 20·전체) "
    "광고 제목·간단 설명을 주시면 분석이 정확해져요(선택)'라고 한 번만 되묻는다.\n"
    "  [이전 대화]에 이미 그 되물음이 있고 이번 메시지가 그 답(또는 '그냥/기본/아무거나')이거나, "
    "이번 메시지·[이전 대화]에 표본·타깃·제목·설명·목표가 있으면, 그 값(표본·타깃 없으면 기본 "
    "표본20·전체, 제목·설명은 ad_title·ad_description에 반영)으로 바로 실행한다.\n"
    "  실행 후 결과의 persisted가 false면 '프로젝트 미선택으로 결과가 저장되지 않았어요 — "
    "나중에 조회하려면 프로젝트를 선택해 다시 돌려주세요'라고 반드시 안내한다.\n"
    "  사용한 설정을 답에 명시하고 다른 설정을 원하면 함께 말해달라고 안내한다.\n"
    "  맥락에 첨부된 광고가 없으면 start_simulation을 호출하지 말고 먼저 이미지 첨부를 요청한다.\n"
    "- 페르소나 토론(debate)은 시뮬 결과와 별개 산출물이다. '토론 현황/목록'은 "
    "sim_debate_list(simulation_id)로, 특정 토론 상세(참가자·발언·판정)는 "
    "sim_debate_detail(debate_id)로 조회한다. '토론 돌려/시작'은 start_debate(simulation_id)로 "
    "트리거하되 완료된 시뮬이 있어야 하고 백그라운드라 '완료 후 토론 목록으로 확인'이라 안내한다. "
    "토론 내용이 없다고 단정하지 말고 먼저 이 툴들로 확인한다.\n"
    "- '신뢰할 수 있나'는 신뢰구간·effective_n·QA·variance_warning을 근거로 설명하고, "
    "방향성은 신뢰 가능하나 절대값 단언은 피한다고 안내한다.\n"
    "- 예측(상대)과 실측(절대)을 수치로 환산하지 말 것. 근거 없으면 모른다고 답한다.\n"
    "문장 끝에 콜론을 쓰지 말 것."
)


def _context_note(state: dict) -> str:
    """현재 맥락(첨부 광고·시뮬 id)을 LLM에 노출 — 안 보여주면 LLM이 첨부 유무를 모른다."""
    notes = []
    if state.get("ad_id"):
        notes.append("첨부된 광고 있음(이미지 포함) — 시뮬 실행 가능(start_simulation).")
    if state.get("simulation_id"):
        notes.append("현재 맥락 simulation_id 보유 — 그 시뮬 조회 가능.")
    return ("\n\n[현재 맥락]\n- " + "\n- ".join(notes)) if notes else ""


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
    _svc: dict = {}  # 지연 생성 sim 서비스 — 트리거(start_simulation) 실제 호출 시에만 build

    class _State(MessagesState, total=False):
        simulation_id: str | None
        organization_id: str | None  # 서버 결정론 스코프(LLM 산출 무시) — 테넌트 격리
        ad_id: str | None  # 첨부 광고(트리거 대상) — 서버 주입
        ad_image_url: str | None
        ad_image_key: str | None
        project_id: str | None
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

    @tool
    async def start_simulation(
        sample_size: int = 20,
        target_age_min: int | None = None,
        target_age_max: int | None = None,
        target_gender: str | None = None,
        ad_title: str | None = None,
        ad_objective: str | None = None,
        product_category: str | None = None,
        ad_description: str | None = None,
        ad_id: str | None = None,
        ad_image_url: str | None = None,
        ad_image_key: str | None = None,
        project_id: str | None = None,
        org_id: str | None = None,
    ) -> dict:
        """광고 시뮬레이션을 실제로 실행(큐 트리거)한다. 첨부 광고(ad_id)가 있을 때만.

        실행 전 표본수·타깃(연령/성별)·제목·목표를 사용자에게 확인하라. 사용자가 값을 안 주거나
        '그냥 돌려'라고 하면 기본(표본 20·전체 타깃)으로 실행하되 사용한 설정을 답에 명시한다.
        ad_id·이미지·project·org는 서버가 주입 — LLM은 채우지 않는다.
        """
        if not ad_id:
            return {"error": "need_ad", "message": "먼저 광고 이미지를 첨부해 주세요."}
        from domain.simulation.contracts.schemas import SimulationRunRequest  # noqa: PLC0415

        if "svc" not in _svc:
            from domain.simulation.wiring import build_simulation_service  # noqa: PLC0415

            _svc["svc"] = build_simulation_service(settings)
        tf: dict = {}
        if target_age_min is not None:
            tf["age_min"] = target_age_min
        if target_age_max is not None:
            tf["age_max"] = target_age_max
        if target_gender:
            tf["gender"] = target_gender
        req = SimulationRunRequest(
            ad_id=ad_id,
            ad_image_url=ad_image_url,
            ad_image_key=ad_image_key,
            sample_size=sample_size,
            target_filter=tf or None,
            ad_title=ad_title,
            ad_objective=ad_objective,
            product_category=product_category,
            ad_content=ad_description,  # 사용자가 준 광고 설명 → 분석 입력(VLM 보강)
            project_id=project_id,
            organization_id=org_id,
        )
        run_id = await _svc["svc"].start(req)
        return {
            "run_id": run_id,
            "sample_size": sample_size,
            "target": tf or "전체(AUTO)",
            "ad_title": ad_title,
            "persisted": bool(project_id),
        }

    @tool
    async def sim_debate_list(simulation_id: str | None = None) -> dict:
        """이 시뮬레이션의 페르소나 토론 목록(주제·상태·결론 요약)을 조회한다."""
        if not simulation_id:
            return {"error": "need_simulation_id"}
        return await sim_tools.sim_debate_list(simulation_id)

    @tool
    async def sim_debate_detail(debate_id: str) -> dict:
        """특정 토론의 상세(참가자·라운드별 발언·판정)를 조회한다."""
        return await sim_tools.sim_debate_detail(debate_id)

    @tool
    async def start_debate(simulation_id: str | None = None) -> dict:
        """완료된 시뮬레이션의 반응으로 페르소나 토론을 백그라운드로 시작(트리거)한다."""
        if not simulation_id:
            return {"error": "need_simulation_id"}
        return await sim_tools.start_debate(simulation_id)

    tools = [
        sim_result,
        sim_persona_basis,
        sim_list,
        sim_find_by_name,
        search_kb,
        start_simulation,
        sim_debate_list,
        sim_debate_detail,
        start_debate,
    ]
    bound = llm.bind_tools(tools)
    by_name = {t.name: t for t in tools}

    async def agent(state: _State) -> dict:
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=_SYSTEM + _context_note(state)), *msgs]
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
            _ctx_sim_tools = ("sim_result", "sim_persona_basis", "sim_debate_list", "start_debate")
            if name in _ctx_sim_tools and not args.get("simulation_id"):
                args["simulation_id"] = ctx_id
            # org 스코프는 서버가 결정론 주입(LLM 산출 무시) — 테넌트 격리.
            if name in ("sim_list", "sim_find_by_name"):
                args["org_id"] = org_id
            # 트리거: 광고/스코프 식별자는 서버가 컨텍스트에서 강제 주입(LLM은 표본·타깃만 채움).
            if name == "start_simulation":
                args["ad_id"] = state.get("ad_id")
                args["ad_image_url"] = state.get("ad_image_url")
                args["ad_image_key"] = state.get("ad_image_key")
                args["project_id"] = state.get("project_id")
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
                "ad_id": (context_ids or {}).get("ad_id"),
                "ad_image_url": (context_ids or {}).get("ad_image_url"),
                "ad_image_key": (context_ids or {}).get("ad_image_key"),
                "project_id": (context_ids or {}).get("project_id"),
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
