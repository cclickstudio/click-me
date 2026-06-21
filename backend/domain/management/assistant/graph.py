# 매니지먼트 에이전틱 RAG 그래프 — CRAG-lite (route→retrieve→grade→재검색→generate)
"""LangGraph 오케스트레이션. 숫자는 실시간 툴(실측), 가이드는 KB(벡터)에서 근거+인용.

근거가 부족하면 grade가 재검색을 1회 더 돌린다(self-correction). 생성은 검색된 근거만 사용하고
수치는 반드시 live에서 인용한다(환각 방지).
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from domain.management.assistant.actions import suggest_action
from domain.management.assistant.contracts import AskResult, Citation
from domain.management.assistant.tools import INTENT_TOOLS

_MAX_RETRIES = 1


class _State(TypedDict, total=False):
    question: str
    campaign_id: str | None
    ad_id: str | None
    intent: str
    needs_live: bool
    needs_kb: bool
    live: dict
    kb: list[dict]
    attempts: int
    used_tools: list[str]
    answer: str


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출(코드펜스 허용). 실패하면 빈 dict."""
    t = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(t)
    except (ValueError, TypeError):
        return {}


async def _chat(llm, system: str, user: str) -> str:
    resp = await llm.ainvoke([("system", system), ("human", user)])
    return resp.content if isinstance(resp.content, str) else str(resp.content)


_ROUTE_SYS = (
    "너는 광고 매니지먼트 질문 라우터다. 질문을 보고 어떤 실시간 데이터와 지식이 필요한지 "
    "JSON으로만 답하라. 키: intent(campaigns|budget|before_after|campaign_detail|general), "
    "needs_live(bool), needs_kb(bool). 수치/현황 질문은 needs_live=true, "
    "원인·방법·정책 질문은 needs_kb=true. 둘 다면 둘 다 true."
)
_GRADE_SYS = (
    "너는 근거 충분성 평가자다. 질문과 수집된 근거(live+kb)를 보고 답하기에 충분한지 "
    'JSON으로만: {"sufficient": true|false}. 근거가 비었거나 질문과 무관하면 false.'
)
_GEN_SYS = (
    "너는 광고 매니지먼트 애널리스트 CLIO다. 한국어로 간결하게 답한다. "
    "수치는 반드시 live 근거에서만 인용하고(추정·환각 금지), 원인·방법은 kb 근거로 설명한다. "
    "예측(상대 지표)과 실측(절대)을 수치 환산하지 말 것. 근거가 없으면 모른다고 말한다. "
    "행동(일시중지·게재시작·증액 등)은 제안만 하고 실행하지 않는다(실행은 승인 경로). "
    "문장 끝에 콜론을 쓰지 말 것."
)


def build_graph(settings, retriever, llm):
    """CRAG-lite 그래프 컴파일 — retriever(KB), llm(route/grade/generate) 주입."""

    async def route(state: _State) -> dict:
        out = _parse_json(await _chat(llm, _ROUTE_SYS, state["question"]))
        intent = out.get("intent", "general")
        if state.get("campaign_id") and intent in ("general", "campaigns"):
            intent = "campaign_detail"
        return {
            "intent": intent,
            "needs_live": bool(out.get("needs_live", True)),
            "needs_kb": bool(out.get("needs_kb", True)),
            "attempts": 0,
            "used_tools": [],
            "live": {},
            "kb": [],
        }

    async def retrieve(state: _State) -> dict:
        used = list(state.get("used_tools", []))
        live = dict(state.get("live", {}))
        kb = list(state.get("kb", []))
        if state.get("needs_live"):
            name, fn = INTENT_TOOLS.get(state["intent"], INTENT_TOOLS["campaigns"])
            if name == "live_campaign_detail":
                live = await fn(settings, state.get("campaign_id") or "")
            else:
                live = await fn(settings)
            if name not in used:
                used.append(name)
        if state.get("needs_kb") and retriever is not None:
            k = 4 + state.get("attempts", 0) * 3  # 재검색 시 폭 확대
            try:
                kb = await retriever.search(state["question"], k=k)
            except Exception:  # noqa: BLE001 — KB 미적재/조회 실패면 live만으로 진행
                kb = []
        return {"live": live, "kb": kb, "used_tools": used}

    async def grade(state: _State) -> dict:
        ctx = json.dumps(
            {"live": state.get("live"), "kb": [d["title"] for d in state.get("kb", [])]},
            ensure_ascii=False,
        )
        out = _parse_json(await _chat(llm, _GRADE_SYS, f"질문: {state['question']}\n근거: {ctx}"))
        if not out.get("sufficient", True) and state.get("attempts", 0) < _MAX_RETRIES:
            return {"attempts": state.get("attempts", 0) + 1, "needs_kb": True}
        return {"attempts": -1}  # -1 = 충분/한도 → generate

    async def generate(state: _State) -> dict:
        kb_text = "\n\n".join(
            f"[{d['source']}] {d['title']}\n{d['chunk']}" for d in state.get("kb", [])
        )
        user = (
            f"질문: {state['question']}\n\n"
            f"[실측 근거(live)]\n{json.dumps(state.get('live', {}), ensure_ascii=False)}\n\n"
            f"[지식 근거(kb)]\n{kb_text or '(없음)'}"
        )
        return {"answer": await _chat(llm, _GEN_SYS, user)}

    def after_grade(state: _State) -> str:
        return "generate" if state.get("attempts", 0) < 0 else "retrieve"

    g = StateGraph(_State)
    g.add_node("route", route)
    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade)
    g.add_node("generate", generate)
    g.set_entry_point("route")
    g.add_edge("route", "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", after_grade, {"retrieve": "retrieve", "generate": "generate"})
    g.add_edge("generate", END)
    return g.compile()


def to_result(state: dict[str, Any]) -> AskResult:
    """그래프 최종 state → AskResult(인용·근거 포함)."""
    citations = [Citation(kind="live", source=t) for t in state.get("used_tools", [])]
    citations += [
        Citation(kind="kb", source=d["source"], title=d["title"]) for d in state.get("kb", [])
    ]
    return AskResult(
        answer=state.get("answer", ""),
        citations=citations,
        used_tools=list(state.get("used_tools", [])),
        evidence=state.get("live", {}) or {},
        suggested_action=suggest_action(state.get("question", ""), state.get("campaign_id")),
    )
