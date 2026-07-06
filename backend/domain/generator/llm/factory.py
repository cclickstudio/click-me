"""텍스트 LLM 팩토리 — 프로바이더 추상화.

노드들이 직접 `ChatOpenAI`를 만들지 않고 이 팩토리를 거치게 해서,
`.env`의 `GENERATOR_TEXT_PROVIDER` / `GENERATOR_TEXT_MODEL` 한 줄로 모델을 교체한다.
- openai: `ChatOpenAI` (회사 OpenAI-호환 엔드포인트는 `GENERATOR_TEXT_BASE_URL`로 분기)
- 그 외: LangChain `init_chat_model` 범용 초기화 (해당 통합이 설치된 경우)
"""

from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from core.config import settings

# 일시적(재시도 가치 있는) 예외 모음 — 429(RateLimit)·타임아웃·연결오류·5xx.
# provider SDK가 설치돼 있을 때만 담는다(미설치 provider는 조용히 건너뜀).
_TRANSIENT_EXC: tuple[type[Exception], ...] = ()
try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
    )

    _TRANSIENT_EXC += (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
except Exception:  # noqa: BLE001 — openai 미설치·인터페이스 변경 시 재시도만 생략
    pass
try:
    from google.genai.errors import ServerError as _GenAIServerError

    _TRANSIENT_EXC += (_GenAIServerError,)
except Exception:  # noqa: BLE001 — google-genai 미설치 시 생략
    pass


def with_llm_retry(runnable: Runnable, *, attempts: int = 3) -> Runnable:
    """LLM 호출에 지수백오프+지터 재시도를 씌운다(일시적 오류만 재시도, 잘못된 요청은 즉시 전파).

    구조화 출력 등 '최종' Runnable에 적용해야 한다 — 순서는 모델 → with_structured_output → 재시도.
    (with_retry 결과에는 with_structured_output이 없으므로 반대로 감으면 안 된다.)
    """
    if not _TRANSIENT_EXC:
        return runnable
    return runnable.with_retry(
        retry_if_exception_type=_TRANSIENT_EXC,
        stop_after_attempt=attempts,
        wait_exponential_jitter=True,
    )


def build_text_llm(temperature: float, max_tokens: int | None = None) -> BaseChatModel:
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
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return ChatOpenAI(**kwargs)

    kwargs = {"model_provider": provider, "temperature": temperature, "max_tokens": max_tokens}
    # Gemini 2.5 계열은 thinking이 기본 ON → 추론 토큰이 max_tokens를 잠식해 구조화 출력이 잘린다.
    # thinking_budget=0으로 비활성화해 max_tokens가 온전히 출력에 쓰이게 한다.
    if provider == "google_genai":
        kwargs["thinking_budget"] = 0
    return init_chat_model(model, **kwargs)


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
