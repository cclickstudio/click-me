# 슈퍼바이저 LLM 팩토리 — Claude Sonnet 4.6 tool-calling. 키부재/use_mock면 None(키워드 폴백).
"""generator/llm/factory.py 패턴 미러. None 반환 = 그래프가 결정론 키워드 라우팅으로 폴백."""

from __future__ import annotations


def build_supervisor_llm(settings):
    """tool-calling 슈퍼바이저 LLM 또는 None(폴백 신호).

    use_mock=True 또는 anthropic 키 부재면 None → 그래프가 키워드 라우터 사용.
    """
    if getattr(settings, "use_mock", True) or not getattr(settings, "anthropic_api_key", None):
        return None

    from langchain.chat_models import init_chat_model

    return init_chat_model(
        settings.chat_orchestrator_model,
        model_provider=settings.chat_orchestrator_provider,
        temperature=settings.chat_orchestrator_temperature,
    )
