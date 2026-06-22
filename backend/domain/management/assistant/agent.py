# 매니지먼트 어시스턴트 진입점 — build_management_agent(settings) → ask(req) -> AskResult
"""오케스트레이터가 부를 단일 진입점. 키+실모드면 CRAG-lite 그래프(LLM+KB), 아니면 결정론 폴백.

폴백은 키·임베딩 없이도 동작(게이트 #9 재현성) — mock reader로 실시간 툴만 요약한다.
"""

from __future__ import annotations

from domain.management.assistant.actions import suggest_action
from domain.management.assistant.contracts import AskRequest, AskResult, Citation
from domain.management.assistant.tools import INTENT_TOOLS


def _keyword_intent(q: str, campaign_id: str | None) -> str:
    if campaign_id:
        return "campaign_detail"
    if any(k in q for k in ("예산", "소진", "런레이트", "페이싱", "budget")):
        return "budget"
    if any(k in q for k in ("예측", "비교", "전후", "before")):
        return "before_after"
    if any(k in q for k in ("왜", "게재", "안 나", "원인", "거절", "심사")):
        return "campaign_detail"
    return "campaigns"


def _summarize(intent: str, live: dict) -> str:
    """폴백 요약 — 실측 dict를 한국어 한두 줄로."""
    if live.get("error") == "rate_limited":
        return "Meta 요청 한도에 걸렸습니다. 잠시 후 다시 시도하세요."
    if intent == "budget":
        return (
            f"{live.get('period', '')} 이번 달 소진 ₩{live.get('this_month_spent_krw', 0):,} · "
            f"이 페이스면 월말 예상 ₩{live.get('runrate_projection_krw', 0):,} · "
            f"여력(Meta 선불) ₩{live.get('account_balance_krw', 0):,}."
        )
    if intent == "campaigns":
        cs = live.get("campaigns", [])
        head = ", ".join(f"{c['name']}(CTR {c['ctr'] * 100:.1f}%)" for c in cs[:5])
        return (
            f"운영 캠페인 {live.get('count', 0)}개. {head}"
            if cs
            else "운영 중인 캠페인이 없습니다."
        )
    if intent == "before_after":
        its = live.get("items", [])
        head = "; ".join(f"{i['name']}: {i['verdict']}" for i in its[:5])
        return f"예측 대비 실측: {head}" if its else "비교할 캠페인이 없습니다."
    if intent == "campaign_detail":
        return (
            f"상태 {live.get('effective_status', '?')} · CTR {live.get('ctr', 0) * 100:.2f}% · "
            f"지출 ₩{live.get('spend_krw', 0):,}"
            + (f" · 이슈 {live['issues']}" if live.get("issues") else "")
        )
    return "요청을 이해하지 못했습니다."


def build_management_agent(settings):
    """async ask(AskRequest) -> AskResult. 오케스트레이터/엔드포인트 공용 진입점."""
    api_key = getattr(settings, "openai_api_key", None)
    use_mock = getattr(settings, "use_mock", True)

    if use_mock or not api_key:
        # 폴백 — 키워드 라우팅 + 실시간 툴 요약(LLM·임베딩 없음).
        async def _ask_fallback(req: AskRequest) -> AskResult:
            intent = _keyword_intent(req.question, req.campaign_id)
            name, fn = INTENT_TOOLS[intent]
            live = await (
                fn(settings, req.campaign_id or "")
                if name == "live_campaign_detail"
                else fn(settings)
            )
            return AskResult(
                answer=_summarize(intent, live),
                citations=[Citation(kind="live", source=name)],
                used_tools=[name],
                evidence=live,
                suggested_action=suggest_action(req.question, req.campaign_id),
            )

        return _ask_fallback

    # 풀모드 — Tool-calling ReAct 그래프(LLM 자율 도구 선택 + pgvector KB + HITL)
    from uuid import uuid4  # noqa: PLC0415

    from langchain_core.messages import HumanMessage  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 있을 때만 로드

    from domain.management.assistant.contracts import SuggestedAction  # noqa: PLC0415
    from domain.management.assistant.graph import build_graph, to_result  # noqa: PLC0415
    from domain.management.assistant.retriever import KbRetriever  # noqa: PLC0415
    from domain.management.wiring import build_checkpointer  # noqa: PLC0415

    model = getattr(settings, "management_assistant_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0.0, api_key=api_key)
    retriever = KbRetriever(api_key=api_key)
    graph = build_graph(settings, retriever, llm, checkpointer=build_checkpointer(settings))

    async def _ask(req: AskRequest) -> AskResult:
        thread_id = uuid4().hex
        config = {
            "configurable": {"thread_id": thread_id},
            "run_name": "management_assistant",
            # part-a/3k — 2인 매니지먼트 중 A파트(감지·진단·승인) 소유 표시. LangSmith 태그 필터용.
            "tags": ["management", "assistant", "part-a", "3k"],
            "metadata": {"campaign_id": req.campaign_id, "ad_id": req.ad_id},
        }
        final = await graph.ainvoke(
            {
                "messages": [HumanMessage(content=req.question)],
                "campaign_id": req.campaign_id,
            },
            config=config,
        )
        # interrupt로 멈춘 경우 — 위험 액션이 사람 승인 게이트에서 멈췄다(HITL)
        interrupts = final.get("__interrupt__")
        if interrupts:
            payload = interrupts[0].value or {}
            sa_dict = payload.get("suggested_action", {})
            sa = SuggestedAction(**sa_dict) if sa_dict else None
            return AskResult(
                answer=(
                    f"{sa.rationale} 승인하시면 실행 경로로 진행됩니다."
                    if sa
                    else "사람 승인이 필요한 작업입니다."
                ),
                used_tools=list(final.get("used_tools", [])),
                evidence=final.get("live_evidence", {}) or {},
                suggested_action=sa,
                requires_approval=True,
                thread_id=thread_id,
            )
        return to_result(final, thread_id)

    return _ask
