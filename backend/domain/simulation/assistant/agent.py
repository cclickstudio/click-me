# 시뮬 어시스턴트 진입점 — build_simulation_agent(settings) → ask(req) -> AssistantResult
"""오케스트레이터가 부를 단일 진입점. 키+실모드면 ReAct 그래프(LLM+KB), 아니면 결정론 폴백.

폴백은 키·임베딩 없이 동작 — simulation_id가 있으면 저장된 결과를 KPI로 요약한다(KB 검색은 실모드).
"""

from __future__ import annotations

from core.assistant import AssistantRequest, AssistantResult, Citation
from domain.simulation.assistant.tools import fetch_simulation_result


def _summarize_result(ev: dict) -> str:
    """결과 evidence dict → 한국어 KPI 한 줄 요약(폴백용)."""
    if ev.get("error") == "not_found":
        return "해당 시뮬레이션 결과를 찾을 수 없습니다."
    if ev.get("error") == "invalid_id":
        return "시뮬레이션 ID 형식이 올바르지 않습니다."
    parts: list[str] = []
    cir = ev.get("click_intent_rate")
    if cir is not None:
        lo = (ev.get("ci_low") or 0) * 100
        hi = (ev.get("ci_high") or 0) * 100
        parts.append(f"클릭 의향률 {cir * 100:.1f}% [{lo:.0f}~{hi:.0f}%]")
    if ev.get("purchase_intent") is not None:
        parts.append(f"구매의도 {ev['purchase_intent']:.2f}/5")
    if ev.get("trust_avg") is not None:
        parts.append(f"신뢰도 {ev['trust_avg']:.2f}/5")
    if ev.get("rejection_rate") is not None:
        parts.append(f"거부율 {ev['rejection_rate'] * 100:.1f}%")
    fit = ev.get("objective_fit") or {}
    tail = f" · 목표적합도 {fit.get('grade')}" if fit.get("grade") else ""
    return (" · ".join(parts) + tail) if parts else "결과 수치가 비어 있습니다."


def build_simulation_agent(settings):
    """async ask(AssistantRequest) -> AssistantResult. 오케스트레이터/엔드포인트 공용 진입점."""
    api_key = getattr(settings, "openai_api_key", None)
    use_mock = getattr(settings, "use_mock", True)

    # ── 폴백 — 결과 요약만(LLM·임베딩 없음). simulation_id 없으면 안내 ──
    if use_mock or not api_key:

        async def _ask_fallback(req: AssistantRequest) -> AssistantResult:
            if not req.context_id:
                return AssistantResult(
                    answer="시뮬레이션 결과 ID가 있으면 4대 KPI를 요약해 드립니다."
                    " (KPI 정의·해석 검색은 실모드에서 동작합니다.)"
                )
            ev = await fetch_simulation_result(req.context_id)
            return AssistantResult(
                answer=_summarize_result(ev),
                citations=[Citation(kind="result", source="get_simulation_result")],
                used_tools=["get_simulation_result"],
                evidence=ev,
            )

        return _ask_fallback

    # ── 풀모드 — Tool-calling ReAct 그래프(결과조회 + pgvector KB) ──
    from langchain_core.messages import AIMessage, HumanMessage  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 있을 때만 로드

    from domain.simulation.assistant.graph import build_graph, to_result  # noqa: PLC0415
    from domain.simulation.assistant.retriever import SimKbRetriever  # noqa: PLC0415

    model = getattr(settings, "simulation_assistant_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0.0, api_key=api_key)
    retriever = SimKbRetriever(api_key=api_key)
    graph = build_graph(settings, retriever, llm)

    async def _ask(req: AssistantRequest) -> AssistantResult:
        config = {
            "run_name": "simulation_assistant",
            "tags": ["simulation", "assistant"],
            "metadata": {"simulation_id": req.context_id, "ad_id": req.ad_id},
        }
        # 시드에 프로젝트 ID·시뮬 ID를 실어 LLM이 list/get 도구 인자로 쓰게 한다.
        prefix = ""
        if req.project_id:
            prefix += f"[프로젝트 ID: {req.project_id}] "
        if req.context_id:
            prefix += f"[시뮬레이션 ID: {req.context_id}] "
        # 직전 대화(최근 6개)를 맥락으로 앞에 붙인다(후속 질문 자연스럽게).
        hist = [
            (AIMessage if role == "assistant" else HumanMessage)(content=content)
            for role, content in (req.history or [])[-6:]
        ]
        final = await graph.ainvoke(
            {"messages": [*hist, HumanMessage(content=prefix + req.question)]}, config=config
        )
        return to_result(final)

    return _ask
