# 생성 어시스턴트 진입점 — build_generator_agent(settings) → ask(req) -> AssistantResult
"""오케스트레이터가 부를 단일 진입점. 키+실모드면 ReAct 그래프(LLM+KB), 아니면 결정론 폴백.

폴백은 키·임베딩 없이 동작 — generation_id가 있으면 후보·전략을 요약한다(KB 검색은 실모드).
"""

from __future__ import annotations

from core.assistant import AssistantRequest, AssistantResult, Citation
from domain.generator.assistant.tools import fetch_generation_result


def _summarize_generation(ev: dict) -> str:
    """결과 evidence dict → 한국어 한 줄 요약(폴백용)."""
    if ev.get("error") == "not_found":
        return "해당 생성 결과를 찾을 수 없습니다."
    status = ev.get("status")
    n = ev.get("candidate_count", 0)
    strategies = [c.get("strategy") for c in (ev.get("candidates") or []) if c.get("strategy")]
    sel = " · 선택된 후보 있음" if ev.get("selected_candidate_id") else ""
    tail = f" · 전략 {', '.join(strategies)}" if strategies else ""
    return f"생성 상태 {status} · 후보 {n}개{sel}{tail}"


def build_generator_agent(settings):
    """async ask(AssistantRequest) -> AssistantResult. 오케스트레이터/엔드포인트 공용 진입점."""
    api_key = getattr(settings, "openai_api_key", None)
    use_mock = getattr(settings, "use_mock", True)

    # ── 폴백 — 결과 요약만(LLM·임베딩 없음). generation_id 없으면 안내 ──
    if use_mock or not api_key:

        async def _ask_fallback(req: AssistantRequest) -> AssistantResult:
            if not req.context_id:
                return AssistantResult(
                    answer="생성 결과 ID가 있으면 후보·전략을 요약해 드립니다."
                    " (카피 전략·원칙 검색은 실모드에서 동작합니다.)"
                )
            ev = await fetch_generation_result(req.context_id)
            return AssistantResult(
                answer=_summarize_generation(ev),
                citations=[Citation(kind="result", source="get_generation_result")],
                used_tools=["get_generation_result"],
                evidence=ev,
            )

        return _ask_fallback

    # ── 풀모드 — Tool-calling ReAct 그래프(결과조회 + pgvector KB) ──
    from langchain_core.messages import HumanMessage  # noqa: PLC0415
    from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 있을 때만 로드

    from domain.generator.assistant.graph import build_graph, to_result  # noqa: PLC0415
    from domain.generator.assistant.retriever import GenKbRetriever  # noqa: PLC0415

    model = getattr(settings, "generator_assistant_model", "gpt-4o-mini")
    llm = ChatOpenAI(model=model, temperature=0.0, api_key=api_key)
    retriever = GenKbRetriever(api_key=api_key)
    graph = build_graph(settings, retriever, llm)

    async def _ask(req: AssistantRequest) -> AssistantResult:
        config = {
            "run_name": "generator_assistant",
            "tags": ["generator", "assistant"],
            "metadata": {"generation_id": req.context_id, "ad_id": req.ad_id},
        }
        # context_id(generation_id)를 질문에 실어 LLM이 get_generation_result 인자로 쓰게 한다.
        seed = f"[생성 ID: {req.context_id}] {req.question}" if req.context_id else req.question
        final = await graph.ainvoke({"messages": [HumanMessage(content=seed)]}, config=config)
        return to_result(final)

    return _ask
