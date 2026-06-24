# 어시스턴트 Composition Root — 도메인 서브에이전트를 레지스트리에 등록
"""오케스트레이터의 mock↔실연동 전환·등록의 유일 지점. 도메인 build 함수를 import해 조립한다.

생성 = 슬롯필링(결정론), 관리 = 에이전틱 RAG(기존). 분류기 LLM은 Gemini(키 있을 때).
"""

from __future__ import annotations

from api.assistant.contracts import Action, Intent, SubagentRequest, SubagentResult
from api.assistant.orchestrator import Orchestrator
from api.assistant.registry import Handler, SubagentRegistry

_GEMINI_MODEL = "gemini-2.5-flash"


def _build_classifier_llm(settings) -> object | None:
    """의도 분류용 Gemini. 키 없으면 None(키워드 폴백)."""
    api_key = getattr(settings, "gemini_api_key", None)
    if not api_key:
        return None
    from langchain_google_genai import ChatGoogleGenerativeAI  # noqa: PLC0415

    model = getattr(settings, "chat_model", _GEMINI_MODEL)
    return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.0)


def _build_management_handler(settings) -> Handler:
    """management 에이전틱 RAG를 공통 계약으로 어댑트(AskRequest/AskResult → SubagentResult)."""
    from domain.management.assistant.agent import build_management_agent  # noqa: PLC0415
    from domain.management.assistant.contracts import AskRequest  # noqa: PLC0415

    ask = build_management_agent(settings)

    async def handle(req: SubagentRequest) -> SubagentResult:
        result = await ask(AskRequest(question=req.last_user_text, ad_id=req.context_ad_id))
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
                {"kind": c.kind, "source": c.source, "title": c.title} for c in result.citations
            ],
            "used_tools": result.used_tools,
            "requires_approval": result.requires_approval,
            "thread_id": result.thread_id,
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
