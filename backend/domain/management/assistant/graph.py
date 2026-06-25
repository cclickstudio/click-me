# 매니지먼트 에이전틱 RAG 그래프 — Tool-calling ReAct + HITL(interrupt)
"""LangGraph ReAct 루프. LLM이 스스로 도구를 골라 실측(live)·지식(KB)을 모은 뒤 답한다.

- 숫자는 실측 도구(live_*)에서만 인용한다(환각 방지). 해석·정책은 search_kb로 근거를 댄다.
- 운영 변경(write)은 propose_action으로 '제안'만 한다. 사람 승인이 필요한 Tier면 interrupt로
  그래프를 멈추고 제어를 사람에게 넘긴다 — 어시스턴트는 writer/executor를 직접 부르지 않는다.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt

from domain.management.approval import judge_tier, requires_human
from domain.management.assistant import tools as live_tools
from domain.management.assistant.actions import _RATIONALE
from domain.management.assistant.contracts import (
    AskResult,
    Citation,
    DiagnosticResult,
    SuggestedAction,
)

#: 도구 호출 라운드 상한 — 초과 시 도구 없이 최종 답을 강제(무한 루프 방지)
_MAX_ROUNDS = 5

_SYSTEM = (
    "너는 광고 매니지먼트 애널리스트 CLIO다. 한국어로 간결하게 답한다.\n"
    "도구를 적극 사용해 근거를 모은 뒤 답하라.\n"
    "- 현황·수치(예산·지출·CTR·ROAS·상태)는 반드시 live 도구(live_campaigns/live_budget/"
    "live_campaign_detail/live_before_after)로 조회해 그 값만 인용한다. 추정·환각 금지.\n"
    "- 원인·방법·정책은 search_kb로 근거를 찾아 설명한다.\n"
    "- 예측(상대 지표)과 실측(절대)을 수치로 환산하지 말 것.\n"
    "- 운영 변경(일시중지·게재시작·증액·감액·소재교체)은 propose_action으로 제안만 한다. "
    "직접 실행하지 않는다(실행은 사람 승인 경로).\n"
    "- 근거가 없으면 모른다고 말한다. 문장 끝에 콜론을 쓰지 말 것."
)


class _State(MessagesState, total=False):
    campaign_id: str | None
    used_tools: list[str]
    kb_citations: list[dict]
    live_evidence: dict
    diagnostic: dict
    suggested_action: dict | None
    tool_rounds: int


def _suggested(action_type: str, campaign_id: str | None) -> SuggestedAction:
    """action_type → SuggestedAction. Tier 판정은 승인 플레인(approval.judge_tier)을 그대로 쓴다."""
    tier = judge_tier(action_type)
    needs = requires_human(tier)
    gate = "사람 승인 필요" if needs else "낮은 위험(자동 승인 한도 내)"
    why = _RATIONALE.get(action_type, action_type)
    return SuggestedAction(
        action_type=action_type,
        target_campaign_id=campaign_id,
        tier=tier.name,
        requires_approval=needs,
        rationale=f"{why} — {gate}. 실행은 승인 경로에서 확인하세요.",
    )


def build_graph(settings, retriever, llm, checkpointer=None):
    """ReAct 그래프 컴파일 — 도구는 settings/retriever를 클로저로 바인딩한다."""

    @tool
    async def live_campaigns() -> dict:
        """운영 중인 모든 캠페인의 목록과 핵심 실측(상태·지출·CTR·ROAS).
        전체 현황·목록 질문에 쓴다."""
        return await live_tools.live_campaigns(settings)

    @tool
    async def live_budget() -> dict:
        """이번 달 예산 소진액·런레이트(월말 예상)·계정 잔액.
        예산·페이싱 질문에 쓴다."""
        return await live_tools.live_budget(settings)

    @tool
    async def live_campaign_detail(campaign_id: str) -> dict:
        """특정 캠페인의 실측과 게재 상태(심사·이슈).
        '왜 안 나가나' 등 단일 캠페인 진단에 쓴다."""
        return await live_tools.live_campaign_detail(settings, campaign_id)

    @tool
    async def live_before_after() -> dict:
        """집행 전(시뮬 예측) vs 후(실측) 방향성을 캠페인별 비교.
        예측 적중·성과 검증 질문에 쓴다."""
        return await live_tools.live_before_after(settings)

    @tool
    async def live_diagnosis(campaign_id: str) -> dict:
        """캠페인 시간별 데이터로 이상 진단(anomaly_type·confidence·hypothesis). 수치는 실측."""
        result = await live_tools.live_diagnosis(settings, campaign_id)
        return result.model_dump(mode="json")

    @tool
    async def search_kb(query: str) -> list[dict]:
        """정책·최적화 플레이북·KPI 규칙 등 지식베이스 근거 문서 검색.
        원인·방법·정책 설명에 쓴다."""
        if retriever is None:
            return []
        try:
            return await retriever.search(query, k=4)
        except Exception:  # noqa: BLE001 — KB 미적재면 빈 결과로 진행(live만으로 답)
            return []

    @tool
    async def propose_action(action_type: str, campaign_id: str | None = None) -> dict:
        """운영 변경을 '제안'한다(실행 안 함). 사람 승인이 필요한 Tier면 그래프가 멈춘다.
        action_type: PAUSE_CAMPAIGN|ACTIVATE_CAMPAIGN|INCREASE_BUDGET|
        DECREASE_BUDGET|REPLACE_CREATIVE."""
        # 본체는 노드에서 인터셉트(interrupt 처리)되어 직접 실행되지 않는다.
        return {"action_type": action_type, "campaign_id": campaign_id}

    read_tools = [
        live_campaigns,
        live_budget,
        live_campaign_detail,
        live_before_after,
        live_diagnosis,
        search_kb,
    ]
    bound = llm.bind_tools([*read_tools, propose_action])
    by_name = {t.name: t for t in read_tools}

    async def agent(state: _State) -> dict:
        msgs = state["messages"]
        if not any(isinstance(m, SystemMessage) for m in msgs):
            msgs = [SystemMessage(content=_SYSTEM), *msgs]
        # 라운드 상한 도달 시 도구 없는 LLM으로 최종 답 강제
        model = bound if state.get("tool_rounds", 0) < _MAX_ROUNDS else llm
        return {"messages": [await model.ainvoke(msgs)]}

    async def tools_node(state: _State) -> dict:
        ai = state["messages"][-1]
        used = list(state.get("used_tools", []))
        kb_cites = list(state.get("kb_citations", []))
        evidence = dict(state.get("live_evidence", {}))
        diagnostic = state.get("diagnostic")
        suggested = state.get("suggested_action")
        out_msgs: list[ToolMessage] = []

        for call in ai.tool_calls:
            name, args, cid = call["name"], call.get("args", {}), call["id"]
            if name == "propose_action":
                action_type = args.get("action_type", "")
                target = args.get("campaign_id") or state.get("campaign_id")
                sa = _suggested(action_type, target)
                if sa.requires_approval:
                    # HITL — 위험 액션 앞에서 사람에게 제어를 넘긴다(checkpointer 필요).
                    interrupt({"suggested_action": sa.model_dump()})
                suggested = sa.model_dump()
                out_msgs.append(
                    ToolMessage(
                        content=json.dumps(sa.model_dump(), ensure_ascii=False), tool_call_id=cid
                    )
                )
                continue

            result = await by_name[name].ainvoke(args)
            if name not in used:
                used.append(name)
            if name == "search_kb":
                kb_cites.extend(result if isinstance(result, list) else [])
            elif name == "live_diagnosis":
                diagnostic = result if isinstance(result, dict) else diagnostic
            else:
                evidence = result if isinstance(result, dict) else evidence
            out_msgs.append(
                ToolMessage(content=json.dumps(result, ensure_ascii=False), tool_call_id=cid)
            )

        return {
            "messages": out_msgs,
            "used_tools": used,
            "kb_citations": kb_cites,
            "live_evidence": evidence,
            "diagnostic": diagnostic,
            "suggested_action": suggested,
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
    return g.compile(checkpointer=checkpointer)


def to_result(state: dict[str, Any], thread_id: str | None = None) -> AskResult:
    """그래프 최종 state → AskResult(인용·근거 포함). 인터럽트 없이 정상 종료한 경우."""
    last = state["messages"][-1] if state.get("messages") else None
    answer = last.content if isinstance(getattr(last, "content", None), str) else ""
    citations = [Citation(kind="live", source=t) for t in state.get("used_tools", [])]
    citations += [
        Citation(kind="kb", source=d["source"], title=d.get("title", ""))
        for d in state.get("kb_citations", [])
    ]
    sa = state.get("suggested_action")
    dx = state.get("diagnostic")
    return AskResult(
        answer=answer,
        citations=citations,
        used_tools=list(state.get("used_tools", [])),
        evidence=state.get("live_evidence", {}) or {},
        suggested_action=SuggestedAction(**sa) if sa else None,
        requires_approval=bool(sa and sa.get("requires_approval")),
        diagnostic=DiagnosticResult.model_validate(dx) if dx else None,
        thread_id=thread_id,
    )
