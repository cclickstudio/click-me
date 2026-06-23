# 광고 생성 에이전틱 RAG 그래프 — Tool-calling ReAct (결과조회 + KB)
"""LangGraph ReAct 루프. LLM이 결과조회(생성 결과)·KB(카피 전략·원칙)를 골라 모은 뒤 답한다.

매니지와 달리 행동 제안(write)·HITL 없음 — 읽기·해석 전용. 사실은 결과조회 도구에서만 인용한다.
"""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph

from core.assistant import AssistantResult, Citation
from domain.generator.assistant import tools as gen_tools

#: 도구 호출 라운드 상한 — 초과 시 도구 없이 최종 답 강제(무한 루프 방지)
_MAX_ROUNDS = 5

_SYSTEM = (
    "너는 광고 생성 분석가 CLIO다. 한국어로 간결하게 답한다.\n"
    "도구로 근거를 모은 뒤 답하라.\n"
    "- 특정 생성 결과(후보·전략·선택·QA)는 get_generation_result로 조회해 "
    "그 값만 인용한다. 추정·환각 금지.\n"
    "- 카피 전략·작성 원칙·브랜드 톤은 search_kb로 근거를 찾아 설명한다.\n"
    "- 근거가 없으면 모른다고 말한다. 문장 끝에 콜론을 쓰지 말 것."
)


class _State(MessagesState, total=False):
    used_tools: list[str]
    kb_citations: list[dict]
    evidence: dict
    tool_rounds: int


def build_graph(settings, retriever, llm):
    """ReAct 그래프 컴파일 — 도구는 retriever를 클로저로 바인딩한다."""

    @tool
    async def get_generation_result(generation_id: str) -> dict:
        """저장된 광고 생성 결과의 후보·전략·선택·QA 요약을 조회한다.
        특정 생성 결과(어떤 시안이 나왔나, 왜 선택됐나)를 묻는 질문에 쓴다."""
        return await gen_tools.fetch_generation_result(generation_id)

    @tool
    async def search_kb(query: str) -> list[dict]:
        """카피 전략·작성 원칙·브랜드 톤 등 생성 지식베이스 근거 문서를 검색한다.
        전략·원칙·"어떤 카피가 좋나" 질문에 쓴다."""
        if retriever is None:
            return []
        try:
            return await retriever.search(query, k=4)
        except Exception:  # noqa: BLE001 — KB 미적재면 빈 결과로 진행(결과 도구만으로 답)
            return []

    read_tools = [get_generation_result, search_kb]
    bound = llm.bind_tools(read_tools)
    by_name = {t.name: t for t in read_tools}

    # 노드 시그니처에 _State를 어노테이트하지 않는다(langgraph 런타임 해석 이슈 회피).
    async def agent(state) -> dict:
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=_SYSTEM), *msgs]
        model = bound if state.get("tool_rounds", 0) < _MAX_ROUNDS else llm
        return {"messages": [await model.ainvoke(msgs)]}

    async def tools_node(state) -> dict:
        ai = state["messages"][-1]
        used = list(state.get("used_tools", []))
        kb_cites = list(state.get("kb_citations", []))
        evidence = dict(state.get("evidence", {}))
        out: list[ToolMessage] = []
        for call in ai.tool_calls:
            name, args, cid = call["name"], call.get("args", {}), call["id"]
            result = await by_name[name].ainvoke(args)
            if name not in used:
                used.append(name)
            if name == "search_kb":
                kb_cites.extend(result if isinstance(result, list) else [])
            else:
                evidence = result if isinstance(result, dict) else evidence
            out.append(
                ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=cid)
            )
        return {
            "messages": out,
            "used_tools": used,
            "kb_citations": kb_cites,
            "evidence": evidence,
            "tool_rounds": state.get("tool_rounds", 0) + 1,
        }

    def route(state) -> str:
        last = state["messages"][-1]
        return "tools" if isinstance(last, AIMessage) and last.tool_calls else END

    g = StateGraph(_State)
    g.add_node("agent", agent)
    g.add_node("tools", tools_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    g.add_edge("tools", "agent")
    return g.compile()


def to_result(state) -> AssistantResult:
    """그래프 최종 state → AssistantResult(인용·근거 포함)."""
    last = state["messages"][-1] if state.get("messages") else None
    answer = last.content if isinstance(getattr(last, "content", None), str) else ""
    citations = [
        Citation(kind="result", source=t) for t in state.get("used_tools", []) if t != "search_kb"
    ]
    citations += [
        Citation(kind="kb", source=d["source"], title=d.get("title", ""))
        for d in state.get("kb_citations", [])
    ]
    return AssistantResult(
        answer=answer,
        citations=citations,
        used_tools=list(state.get("used_tools", [])),
        evidence=state.get("evidence", {}) or {},
    )
