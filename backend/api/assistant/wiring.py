# 어시스턴트 Composition Root — 도메인 서브에이전트를 레지스트리에 등록
"""오케스트레이터의 mock↔실연동 전환·등록의 유일 지점. 도메인 build 함수를 import해 조립한다.

생성 = 슬롯필링(결정론), 관리 = 에이전틱 RAG(기존). 분류기 LLM은 Gemini(키 있을 때).
"""

from __future__ import annotations

from api.assistant.contracts import Action, Intent, SubagentRequest, SubagentResult
from api.assistant.orchestrator import Orchestrator
from api.assistant.registry import Handler, SubagentRegistry

_CLASSIFIER_MODEL = "gpt-4o-mini"


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

    management_handler = _build_management_handler(settings)
    generator_handler = build_generation_chat_agent(settings)
    llm = _build_classifier_llm(settings)

    deep_run = build_deep_agent_graph(llm, management_handler, generator_handler)

    async def run(req: SubagentRequest) -> SubagentResult | None:
        # LLM 없으면(키 미설정) 분류 불가 → CLIO 폴백
        if llm is None:
            return None
        intent = await classify_intent(req, [Intent.MANAGE, Intent.GENERATE], llm=llm)
        if intent == Intent.ADVISE:
            return None
        return await deep_run(req)

    return run
