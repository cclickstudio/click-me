"""텍스트 LLM 팩토리 — 프로바이더 추상화.

노드들이 직접 `ChatOpenAI`를 만들지 않고 이 팩토리를 거치게 해서,
`.env`의 `GENERATOR_TEXT_PROVIDER` / `GENERATOR_TEXT_MODEL` 한 줄로 모델을 교체한다.
- openai: `ChatOpenAI` (회사 OpenAI-호환 엔드포인트는 `GENERATOR_TEXT_BASE_URL`로 분기)
- 그 외: LangChain `init_chat_model` 범용 초기화 (해당 통합이 설치된 경우)
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from core.config import settings


def build_text_llm(temperature: float) -> BaseChatModel:
    """설정된 프로바이더/모델로 통일된 ChatModel을 반환한다."""
    provider = settings.generator_text_provider
    model = settings.generator_text_model

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict = {
            "model": model,
            "api_key": settings.openai_api_key,
            "temperature": temperature,
            "timeout": 120,
        }
        if settings.generator_text_base_url:
            kwargs["base_url"] = settings.generator_text_base_url
        return ChatOpenAI(**kwargs)

    return init_chat_model(model, model_provider=provider, temperature=temperature)


def build_vision_llm(temperature: float) -> BaseChatModel:
    """이미지 입력(vision)용 ChatModel — 텍스트와 별도 프로바이더/모델 설정.

    `GENERATOR_VISION_PROVIDER` / `GENERATOR_VISION_MODEL`로 분기. 비전 지원 모델이어야 한다.
    """
    provider = settings.generator_vision_provider
    model = settings.generator_vision_model

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            temperature=temperature,
        )

    return init_chat_model(model, model_provider=provider, temperature=temperature)
