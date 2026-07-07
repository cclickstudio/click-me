# Anthropic 반응 어댑터(Claude Sonnet 5, 현재 wiring 미사용). 프롬프트·파싱은 gemini 어댑터와 공유.
from __future__ import annotations

import os
from typing import Any

from langsmith import traceable
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from domain.simulation.adapters.gemini._common import (
    _RETRY_ATTEMPTS,
    _RETRY_WAIT_MAX,
    _RETRY_WAIT_MULTIPLIER,
    _is_transient,
    _parse_json,
)
from domain.simulation.adapters.gemini.reaction import generate_reaction
from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction

# 반응 생성 기본 모델(제미나이 2.5 플래시→GPT-4o→Haiku 거쳐 Sonnet 5로 전환).
_DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5"
_MAX_TOKENS = 1536
_FORCE_JSON_SYSTEM = "반드시 아래 요청된 JSON 객체 하나만 출력하라. 설명·코드펜스·추가 텍스트 금지."


def _new_anthropic_client(api_key: str | None) -> Any:
    from anthropic import AsyncAnthropic
    from langsmith.wrappers import wrap_anthropic

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY 미설정 — Anthropic 반응 어댑터 불가")
    return wrap_anthropic(AsyncAnthropic(api_key=key))


class AnthropicReactionEngine:
    """4-b 반응(Anthropic) — Gemini와 동일한 §3.5 JSON을 system 지시로 강제. 5xx 백오프 재시도."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _DEFAULT_ANTHROPIC_MODEL,
        temperature: float = 1.0,
        with_reaction_text: bool = False,
    ) -> None:
        self._client = _new_anthropic_client(api_key)
        self._model = model
        self.version = model
        self._temperature = temperature
        self._with_reaction_text = with_reaction_text  # SSR 배선 시 자유 서술 필드 요구

    @traceable(run_type="llm", name="anthropic.messages_json")
    async def _json_call(self, prompt: str) -> dict:
        resp = None
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            wait=wait_random_exponential(multiplier=_RETRY_WAIT_MULTIPLIER, max=_RETRY_WAIT_MAX),
            stop=stop_after_attempt(_RETRY_ATTEMPTS),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.messages.create(
                    model=self._model,
                    max_tokens=_MAX_TOKENS,
                    temperature=self._temperature,
                    system=_FORCE_JSON_SYSTEM,
                    messages=[{"role": "user", "content": prompt}],
                )
        return _parse_json(resp.content[0].text)

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        return await generate_reaction(
            self._json_call, persona, ad, with_reaction_text=self._with_reaction_text
        )
