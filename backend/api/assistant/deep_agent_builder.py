# 통합 채팅 에이전트 빌더 — create_deep_agent 조립(정책 프롬프트 + tool + 커스텀 상태 + 체크포인터)
"""build_unified_chat_agent(settings) → 컴파일된 LangGraph(astream/ainvoke 가능) | None.

기존 채팅 오케스트레이터(domain/chat)·수제 deep agent를 대체한다.
키 없으면 None(chat.py가 CLIO 폴백). deepagents 부재/충돌 시 create_agent 폴백을 둔다.
"""

from __future__ import annotations

from api.assistant.chat_state import ChatStateMiddleware
from api.assistant.prompts import CHAT_POLICY
from api.assistant.subagent_tools import build_chat_tools


def _has_llm_key(settings) -> bool:
    """답변 LLM provider에 맞는 키가 있는지 — 없으면 에이전트 빌드 불가(폴백)."""
    provider = getattr(settings, "chat_orchestrator_provider", "openai")
    if provider == "anthropic":
        return bool(getattr(settings, "anthropic_api_key", None))
    return bool(getattr(settings, "openai_api_key", None))


def build_unified_chat_agent(settings):
    """통합 채팅 에이전트(create_deep_agent)를 빌드한다. 키 없거나 mock이면 None."""
    if getattr(settings, "use_mock", True) or not _has_llm_key(settings):
        return None

    from domain.chat.llm import build_chat_llm  # noqa: PLC0415
    from domain.management.assistant.memory_store import build_memory_store  # noqa: PLC0415
    from domain.management.wiring import build_checkpointer  # noqa: PLC0415

    model = build_chat_llm(settings, temperature=0.2)  # 기본 Claude Sonnet(provider 설정 따름)
    memory = build_memory_store(settings)
    tools = build_chat_tools(settings, memory=memory)

    try:
        from deepagents import create_deep_agent  # noqa: PLC0415

        return create_deep_agent(
            model=model,
            tools=tools,
            system_prompt=CHAT_POLICY,
            middleware=[ChatStateMiddleware()],
            subagents=[],  # 도메인 위임은 @tool로(충실도) — deepagents 서브에이전트 미사용
            checkpointer=build_checkpointer(settings),
        )
    except Exception as exc:  # noqa: BLE001 — deepagents 부재/충돌 시 create_agent로 폴백
        print(f"[chat] create_deep_agent unavailable, falling back to create_agent: {exc!r}")
        from langchain.agents import create_agent  # noqa: PLC0415

        return create_agent(
            model=model,
            tools=tools,
            system_prompt=CHAT_POLICY,
            middleware=[ChatStateMiddleware()],
            checkpointer=build_checkpointer(settings),
        )
