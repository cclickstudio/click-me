# 어시스턴트 Composition Root — 도메인 서브에이전트를 레지스트리에 등록
"""오케스트레이터의 mock↔실연동 전환·등록의 유일 지점. 도메인 build 함수를 import해 조립한다.

생성 = 슬롯필링(결정론), 관리 = 에이전틱 RAG(기존). 분류기 LLM은 Gemini(키 있을 때).
"""

from __future__ import annotations

import re

from api.assistant.contracts import Action, Intent, SubagentRequest, SubagentResult
from api.assistant.orchestrator import Orchestrator
from api.assistant.registry import Handler, SubagentRegistry

_CLASSIFIER_MODEL = "gpt-4o-mini"

_ADVISE_THRESHOLD = 0.35  # 코사인 유사도 — 미달 시 None(CLIO 폴백). RRF score 아님.
_CITE_PATTERN = re.compile(r"\[([1-9]\d*)\]")  # [1]~[k] 인용 마커
_ADVISE_PROMPT = (
    "다음 근거 문서에 있는 내용만으로 질문에 답하세요. 근거에 없으면 모른다고 답하고 "
    "지어내지 마세요. 정확한 수치가 근거에 없으면 추정·단정하지 마세요. "
    "사용한 문서 번호를 [1][2] 형식으로 본문에 인용하세요.\n\n질문: {q}\n\n근거:\n{ctx}"
)


async def _try_kb_advise(req: SubagentRequest, settings, llm) -> SubagentResult | None:
    """ADVISE 경로 KB 게이트 — 일반지식 KB에 근거 있으면 인용 답변, 없으면 None(CLIO 폴백).

    cosine_score max ≥ 0.35일 때만 LLM 호출(비용↓·환각↓). top-1이 keyword-only(cosine=None)여도
    false negative 안 나게 max로 판정. 인용 마커 누락/범위밖이면 안전 문구로 강등(날조 방지).
    """
    from domain.management.assistant.retriever import (  # noqa: PLC0415
        ADVISE_SOURCE_TYPES,
        KbRetriever,
    )

    retriever = KbRetriever(api_key=getattr(settings, "openai_api_key", None))
    try:
        hits = await retriever.search(req.last_user_text, k=4, source_types=ADVISE_SOURCE_TYPES)
    except Exception:  # noqa: BLE001 — KB 미적재/검색 실패면 CLIO 폴백
        return None
    top_cosine = max((h.get("cosine_score") or 0.0 for h in hits), default=0.0) if hits else 0.0
    if not hits or top_cosine < _ADVISE_THRESHOLD:
        return None

    used = hits[:3]
    ctx = "\n\n".join(f"[{i + 1}] {h['title']}\n{h['chunk']}" for i, h in enumerate(used))
    resp = await llm.ainvoke(_ADVISE_PROMPT.format(q=req.last_user_text, ctx=ctx))
    answer = resp.content if hasattr(resp, "content") else str(resp)

    # 인용 마커 검증 — 없거나 범위 밖이면 출처 문구로 강등(보은 RAG 설계 §11)
    valid = set(range(1, len(used) + 1))
    found = {int(m) for m in _CITE_PATTERN.findall(answer)}
    if not found or not found.issubset(valid):
        answer = answer + "\n\n*(출처: " + ", ".join(h["title"] for h in used) + ")*"

    citations = [
        {
            "kind": "kb",
            "source": h["source"],
            "title": h["title"],
            "trust": h.get("trust"),
            "source_url": h.get("source_url"),
        }
        for h in used
    ]
    return SubagentResult(
        action=Action.ANSWER,
        message=answer,
        meta={
            "source": "management",
            "label": "마케팅 지식 베이스",
            "engine": "GPT-4o-mini · KB",
            "citations": citations,
            "used_tools": ["search_kb"],
            "requires_approval": False,
            "thread_id": None,
            "suggested_action": None,
        },
    )


def _build_classifier_llm(settings) -> object | None:
    """의도 분류용 OpenAI. 키 없으면 None(ADVISE 폴백)."""
    api_key = getattr(settings, "openai_api_key", None)
    if not api_key:
        return None
    from langchain_openai import ChatOpenAI  # noqa: PLC0415

    return ChatOpenAI(model=_CLASSIFIER_MODEL, api_key=api_key, temperature=0.0)


def _build_management_handler(settings) -> Handler:
    """management 에이전틱 RAG를 공통 계약으로 어댑트(AskRequest/AskResult → SubagentResult).

    thread_id는 session_id에서 파생(멀티턴 연속성). suggested_action/evidence도 meta에 포함해
    chat.py가 record_turn 호출에 재사용할 수 있게 한다.
    """
    from domain.management.assistant.agent import build_management_agent  # noqa: PLC0415
    from domain.management.assistant.contracts import AskRequest  # noqa: PLC0415

    ask = build_management_agent(settings)

    async def handle(req: SubagentRequest) -> SubagentResult:
        thread_id = f"mgmt-{req.session_id}" if req.session_id else None
        result = await ask(
            AskRequest(
                question=req.last_user_text,
                ad_id=req.context_ad_id,
                thread_id=thread_id,
                memory_context=req.memory_context,  # M1 — 장기기억(있으면 react가 LLM 맥락 주입)
            )
        )
        answer = result.answer
        if result.suggested_action:
            sa = result.suggested_action
            gate = "사람 승인 필요" if sa.requires_approval else "낮은 위험"
            answer += f"\n\n추천 조치: {sa.action_type} ({gate}) — 실행은 승인 화면에서 확인하세요."
        meta = {
            "source": "management",
            "label": "매니지먼트 어시스턴트",
            "engine": "OpenAI · 실측+KB",
            "citations": [
                {
                    "kind": c.kind,
                    "source": c.source,
                    "title": c.title,
                    "trust": c.trust,
                    "source_url": c.source_url,
                    "as_of": c.as_of,
                }
                for c in result.citations
            ],
            "used_tools": list(result.used_tools),
            "requires_approval": result.requires_approval,
            "thread_id": result.thread_id,
            "suggested_action": (
                result.suggested_action.model_dump() if result.suggested_action else None
            ),
            "evidence": result.evidence,
            "campaigns": (result.evidence or {}).get("campaigns", []),
        }
        return SubagentResult(action=Action.ANSWER, message=answer, meta=meta)

    return handle


def build_assistant(settings) -> Orchestrator:
    """레지스트리 + 오케스트레이터 조립. generate/manage 등록, advise는 폴백(미등록)."""
    from domain.generator.chat import build_generation_chat_agent  # noqa: PLC0415

    registry = SubagentRegistry()
    registry.register(Intent.GENERATE, build_generation_chat_agent(settings))
    registry.register(Intent.MANAGE, _build_management_handler(settings))
    return Orchestrator(registry, classifier_llm=_build_classifier_llm(settings))


def build_deep_agent(settings):
    """Deep Agent 오케스트레이터 조립 — LangGraph 루프 + 서브에이전트 도구 등록.

    반환 함수: run(SubagentRequest) → SubagentResult | None
    None이면 ADVISE — 호출자(chat.py)가 Gemini CLIO로 폴백.
    """
    from api.assistant.deep_agent import build_deep_agent_graph  # noqa: PLC0415
    from api.assistant.intent import classify_intent  # noqa: PLC0415
    from domain.generator.chat import build_generation_chat_agent  # noqa: PLC0415
    from domain.management.wiring import build_checkpointer  # noqa: PLC0415

    management_handler = _build_management_handler(settings)
    generator_handler = build_generation_chat_agent(settings)
    llm = _build_classifier_llm(settings)

    # PG 싱글턴(get_pg_checkpointer) 주입 — management 그래프와 동일 체크포인터 공유(단일화).
    # main.py lifespan에서 init 완료된 싱글턴을 build_checkpointer가 반환(없으면 MemorySaver).
    deep_run = build_deep_agent_graph(
        llm, management_handler, generator_handler, checkpointer=build_checkpointer(settings)
    )

    async def run(req: SubagentRequest) -> SubagentResult | None:
        # LLM 없으면(키 미설정) 분류 불가 → CLIO 폴백
        if llm is None:
            return None
        intent = await classify_intent(req, [Intent.MANAGE, Intent.GENERATE], llm=llm)
        if intent == Intent.ADVISE:
            # KB 게이트 — 일반지식 근거 있으면 인용 답변, 없으면 None(chat.py가 CLIO 폴백).
            return await _try_kb_advise(req, settings, llm)
        return await deep_run(req)

    return run
