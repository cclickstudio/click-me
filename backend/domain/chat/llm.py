# 채팅 답변 LLM 빌더 — provider 설정(anthropic|openai)에 맞는 LangChain 챗 모델을 생성한다.
from typing import Any


def build_chat_llm(
    settings,
    *,
    temperature: float,
    max_tokens: int | None = None,
    timeout: int | None = None,
) -> Any | None:
    """chat_orchestrator_provider(anthropic|openai)에 맞는 챗 모델을 만든다(키 없으면 None).

    답변 생성 전용 — 임베딩·KB 검색은 별도로 OpenAI를 쓴다.
    anthropic이면 ChatAnthropic(max_tokens 필수라 기본 4096), 그 외 ChatOpenAI.
    """
    provider = getattr(settings, "chat_orchestrator_provider", "openai")
    model = getattr(settings, "chat_orchestrator_model", "gpt-4o-mini")
    if provider == "anthropic":
        key = getattr(settings, "anthropic_api_key", None)
        if not key:
            return None
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=model,
            temperature=temperature,
            api_key=key,
            max_tokens=max_tokens or 4096,
        )
    key = getattr(settings, "openai_api_key", None)
    if not key:
        return None
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {"model": model, "temperature": temperature, "api_key": key}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens
    if timeout:
        kwargs["timeout"] = timeout
    return ChatOpenAI(**kwargs)
