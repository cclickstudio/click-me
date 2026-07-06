# 매니지먼트 에이전틱 RAG 그래프 — Tool-calling ReAct + HITL(interrupt)
"""LangGraph ReAct 루프. LLM이 스스로 도구를 골라 실측(live)·지식(KB)을 모은 뒤 답한다.

- 숫자는 실측 도구(live_*)에서만 인용한다(환각 방지). 해석·정책은 search_kb로 근거를 댄다.
- 운영 변경(write)은 propose_action으로 '제안'만 한다. 사람 승인이 필요한 Tier면 interrupt로
  그래프를 멈추고 제어를 사람에게 넘긴다 — 어시스턴트는 writer/executor를 직접 부르지 않는다.
"""

from __future__ import annotations

import contextlib
import json
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel

from domain.management.approval import judge_tier, requires_human
from domain.management.assistant import tools as live_tools
from domain.management.assistant.actions import _RATIONALE
from domain.management.assistant.contracts import AskResult, Citation, SuggestedAction
from domain.management.assistant.retriever import MANAGEMENT_SOURCE_TYPES

#: 도구 호출 라운드 상한 — 초과 시 도구 없이 최종 답을 강제(무한 루프 방지)
_MAX_ROUNDS = 5

_SYSTEM = (
    "너는 광고 매니지먼트 애널리스트 CLIO다. 한국어로 간결하게 답한다.\n"
    "도구를 적극 사용해 근거를 모은 뒤 답하라.\n"
    "- 현황·수치(예산·지출·CTR·ROAS·상태)는 반드시 live 도구(live_campaigns/live_budget/"
    "live_campaign_detail/live_before_after)로 조회해 그 값만 인용한다. 추정·환각 금지.\n"
    "- 주간 정리는 live_weekly_report, 예산 재배분은 live_rebalance_proposal, 이상·피로 점검은 "
    "live_anomaly_scan, 플랫폼·연령성별 분해는 live_campaign_breakdown, 시안은 "
    "live_campaign_creatives, 타깃 설정은 live_campaign_targeting, 리드 명단은 "
    "live_campaign_leads, 오가닉 대비 광고 증분은 live_organic_compare를 쓴다.\n"
    "- 사용자가 캠페인을 이름으로 말하면 live_campaign_find_by_name로 campaign_id를 먼저 찾고, "
    "다건이면 어느 것인지 되묻은 뒤 진행한다.\n"
    "- 원인·방법·정책은 search_kb로 근거를 찾아 설명한다.\n"
    "- 기본은 KB(search_kb) 우선이다. 다만 질문이 최신·시의성 정보를 요구하거나(현재 추세·최근 "
    "변경 등), search_kb 근거가 오래됐거나 불충분하다고 판단되면 web_search로 최신 외부 근거를 "
    "보강한다. 웹 결과는 advisory(참고)이므로 단정하지 말고 출처와 함께 참고로만 인용한다.\n"
    "- 예측(상대 지표)과 실측(절대)을 수치로 환산하지 말 것.\n"
    "- 운영 변경(일시중지·게재시작·증액·감액·소재교체)은 propose_action으로 제안만 한다. "
    "직접 실행하지 않는다(실행은 사람 승인 경로).\n"
    "- 근거가 없으면 모른다고 말한다. 문장 끝에 콜론을 쓰지 말 것."
)


# ── 자기교정 검색(CRAG-lite) — 근거를 평가하고 부족하면 재작성·재검색·신호 ──
_INSUFFICIENT_SOURCE = "_insufficient"  # 인용에서 제외되는 신호 엔트리


class _KbGrade(BaseModel):
    """검색 근거 평가 — 충분성 + (부족 시) 재작성 쿼리."""

    sufficient: bool
    rewrite: str | None = None


async def _grade_kb(llm, query: str, hits: list[dict]) -> _KbGrade:
    """근거가 질문에 충분한지 LLM으로 평가. 실패하면 충분으로 간주(채팅 안 막음)."""
    digest = "; ".join(f"{h.get('title', '')}: {h.get('chunk', '')[:80]}" for h in hits[:4])
    system = (
        "너는 검색 근거 평가자다. 사용자 질문에 대해 검색된 근거가 답하기에 충분한지 판단한다.\n"
        "- 질문의 핵심에 답할 정보가 근거에 있으면 sufficient=true.\n"
        "- 부족하거나 빗나갔으면 sufficient=false, 재검색용 한국어 재작성 쿼리를 rewrite에 제시."
    )
    try:
        structured = llm.with_structured_output(_KbGrade)
        return await structured.ainvoke(
            [("system", system), ("human", f"질문: {query}\n근거: {digest}")],
            # langsmith:nostream — 통합 채팅(deep agent)이 이 서브그래프를 tool로 부를 때
            # 이 내부 grade 호출의 {"sufficient,rewrite} JSON이 stream_mode="messages"로
            # 새어 답변 앞에 붙던 문제 차단(사용자엔 최종 답변만 스트리밍).
            config={
                "run_name": "management:grade_kb",
                "tags": ["management", "crag", "langsmith:nostream"],
            },
        )
    except Exception:  # noqa: BLE001 — 평가 실패는 통과(보수적: 확실한 부족일 때만 교정)
        return _KbGrade(sufficient=True)


def _dedup(hits: list[dict]) -> list[dict]:
    """(source, title) 기준 중복 제거 — 재검색 병합 시 같은 청크 중복 방지."""
    seen: set = set()
    out: list[dict] = []
    for h in hits:
        key = (h.get("source"), h.get("title"))
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


class _State(MessagesState, total=False):
    campaign_id: str | None
    used_tools: list[str]
    kb_citations: list[dict]
    live_evidence: dict
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
    async def live_campaign_find_by_name(name: str) -> dict:
        """캠페인을 '이름'으로 부분일치(대소문자 무시) 검색해 campaign_id를 해소한다.
        사용자가 캠페인을 이름으로 지칭하면 먼저 이 툴로 후보를 찾고, 다건이면 되묻고,
        상세가 필요하면 그 campaign_id로 live_campaign_detail을 쓴다."""
        return await live_tools.live_campaign_find_by_name(settings, name)

    @tool
    async def live_before_after() -> dict:
        """집행 전(시뮬 예측) vs 후(실측) 방향성을 캠페인별 비교.
        예측 적중·성과 검증 질문에 쓴다."""
        return await live_tools.live_before_after(settings)

    @tool
    async def live_weekly_report() -> dict:
        """최근 7일 주간 성과 리포트 — 총합·캠페인별 표·하이라이트·다음 액션.
        '주간 리포트/이번 주 성과 정리' 질문에 쓴다."""
        return await live_tools.live_weekly_report(settings)

    @tool
    async def live_rebalance_proposal() -> dict:
        """캠페인 간 일예산 리밸런싱 제안 — 저효율(높은 CPC)→고효율로 20% 이동 제안(실행 아님).
        '예산 재배분/리밸런싱 어떻게' 질문에 쓴다. 적용은 승인 경로."""
        return await live_tools.live_rebalance_proposal(settings)

    @tool
    async def live_anomaly_scan(target_roas: float | None = None) -> dict:
        """실 캠페인 성과 이상·노출 피로 스캔 — 이상 있는 캠페인만 반환.
        '이상 없어?/문제 있는 캠페인 찾아줘' 질문에 쓴다. 사용자가 목표 ROAS를 말했으면
        target_roas로 넘겨라(없으면 피로 신호만 스캔)."""
        return await live_tools.live_anomaly_scan(settings, target_roas)

    @tool
    async def live_campaign_breakdown(campaign_id: str) -> dict:
        """단일 캠페인 분해 실측 — 게재 플랫폼별(FB/IG)과 연령×성별 노출·클릭·지출·도달.
        '어디에/누구한테 잘 나가?' 같은 분해 질문에 쓴다."""
        return await live_tools.live_campaign_breakdown(settings, campaign_id)

    @tool
    async def live_campaign_creatives(campaign_id: str) -> dict:
        """캠페인 대표 크리에이티브(광고 시안 이름·썸네일) 조회."""
        return await live_tools.live_campaign_creatives(settings, campaign_id)

    @tool
    async def live_campaign_targeting(campaign_id: str) -> dict:
        """캠페인 타겟팅 설정(objective·연령·성별) 조회 — '이 캠페인 타깃이 뭐야'에 쓴다."""
        return await live_tools.live_campaign_targeting(settings, campaign_id)

    @tool
    async def live_campaign_leads(campaign_id: str) -> dict:
        """이 캠페인 광고로 제출된 잠재고객(리드) 명단 조회 — 리드 캠페인 전용."""
        return await live_tools.live_campaign_leads(settings, campaign_id)

    @tool
    async def live_organic_compare() -> dict:
        """오가닉 게시물 ↔ 광고 증분(리프트) 비교 보드 — '오가닉 대비 광고 효과' 질문에 쓴다."""
        return await live_tools.live_organic_compare(settings)

    @tool
    async def search_kb(query: str) -> list[dict]:
        """정책·최적화 플레이북·KPI 규칙 등 지식베이스 근거 문서 검색(자기교정).
        근거가 부족하면 쿼리를 재작성해 재검색하고, 그래도 부족하면 신호를 남긴다.
        원인·방법·정책 설명에 쓴다."""
        if retriever is None:
            return []
        try:
            # management 특화 풀만 검색 — 시뮬 도메인 지식 오염 차단.
            hits = await retriever.search(query, k=4, source_types=MANAGEMENT_SOURCE_TYPES)
        except Exception:  # noqa: BLE001 — KB 미적재면 빈 결과로 진행(live만으로 답)
            return []
        if not hits:
            return []
        grade = await _grade_kb(llm, query, hits)
        if grade.sufficient:
            return hits
        # 부족 → 쿼리 재작성 후 1회 재검색·병합·재평가(CRAG-lite)
        if grade.rewrite:
            with contextlib.suppress(Exception):
                hits = _dedup(
                    hits
                    + await retriever.search(
                        grade.rewrite, k=4, source_types=MANAGEMENT_SOURCE_TYPES
                    )
                )
            if (await _grade_kb(llm, query, hits)).sufficient:
                return hits
        # 여전히 부족 → 에이전트에 신호(인용엔 안 섞임 — tools_node가 필터)
        return [
            *hits,
            {
                "source": _INSUFFICIENT_SOURCE,
                "title": "",
                "chunk": (
                    "KB 근거가 부족하다. web_search로 보강하거나, "
                    "충분한 근거가 없으면 모른다고 정직하게 답하라."
                ),
                "trust": None,
            },
        ]

    @tool
    async def web_search(query: str) -> list[dict]:
        """KB에 근거가 없거나 최신·시의성 정보가 필요할 때만 쓰는 웹검색(참고용·advisory).
        먼저 search_kb를 쓰고, 거기서 못 찾을 때 보조로만. 결과는 단정 말고 참고로 인용한다."""
        from domain.management.assistant.web_search import (  # noqa: PLC0415
            web_search as _web_search,
        )

        try:
            return await _web_search(query, k=3, api_key=getattr(settings, "tavily_api_key", None))
        except Exception:  # noqa: BLE001 — 키 없음/실패면 빈 결과로 진행(KB·live만으로 답)
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
        live_campaign_find_by_name,
        live_before_after,
        live_weekly_report,
        live_rebalance_proposal,
        live_anomaly_scan,
        live_campaign_breakdown,
        live_campaign_creatives,
        live_campaign_targeting,
        live_campaign_leads,
        live_organic_compare,
        search_kb,
        web_search,
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
            if name in ("search_kb", "web_search"):
                # _insufficient 신호는 인용에서 제외(에이전트는 ToolMessage로 보고 web/정직 폴백).
                kb_cites.extend(
                    c
                    for c in (result if isinstance(result, list) else [])
                    if c.get("source") != _INSUFFICIENT_SOURCE
                )
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
        Citation(
            kind="web" if d.get("source") == "web" else "kb",
            source=d["source"],
            title=d.get("title", ""),
            trust=d.get("trust"),
            source_url=d.get("source_url"),
            as_of=d.get("as_of"),
        )
        for d in state.get("kb_citations", [])
    ]
    sa = state.get("suggested_action")
    return AskResult(
        answer=answer,
        citations=citations,
        used_tools=list(state.get("used_tools", [])),
        evidence=state.get("live_evidence", {}) or {},
        suggested_action=SuggestedAction(**sa) if sa else None,
        requires_approval=bool(sa and sa.get("requires_approval")),
        thread_id=thread_id,
    )
