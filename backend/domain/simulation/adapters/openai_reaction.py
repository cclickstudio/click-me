# OpenAI 반응 어댑터 — 제미나이 503 폴백용. 프롬프트·파싱은 gemini 어댑터와 공유, LLM 호출만 OpenAI.
from __future__ import annotations

import json
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
)
from domain.simulation.adapters.gemini.reaction import generate_reaction
from domain.simulation.contracts.schemas import AdInterpretation, PersonaReaction

# 고볼륨·구조화 JSON·롤플레이 작업의 스위트스폿(저비용·JSON mode). 환경변수로 교체 가능.
_DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"


def _new_openai_client(api_key: str | None) -> Any:
    from openai import AsyncOpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — OpenAI 폴백 어댑터 불가")
    return AsyncOpenAI(api_key=key)


class OpenAIReactionEngine:
    """4-b 반응(OpenAI) — Gemini와 동일한 §3.5 JSON을 JSON mode로 산출. 503/5xx 백오프 재시도."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _DEFAULT_OPENAI_MODEL,
        temperature: float = 1.0,
        with_reaction_text: bool = False,
    ) -> None:
        self._client = _new_openai_client(api_key)
        self._model = model
        self.version = model
        self._temperature = temperature
        self._with_reaction_text = with_reaction_text  # SSR 배선 시 자유 서술 필드 요구

    @traceable(run_type="llm", name="openai.chat_json")
    async def _json_call(self, prompt: str) -> dict:
        resp = None
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            wait=wait_random_exponential(multiplier=_RETRY_WAIT_MULTIPLIER, max=_RETRY_WAIT_MAX),
            stop=stop_after_attempt(_RETRY_ATTEMPTS),
            reraise=True,
        ):
            with attempt:
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self._temperature,
                    response_format={"type": "json_object"},
                )
        return json.loads(resp.choices[0].message.content or "{}")

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        return await generate_reaction(
            self._json_call, persona, ad, with_reaction_text=self._with_reaction_text
        )
