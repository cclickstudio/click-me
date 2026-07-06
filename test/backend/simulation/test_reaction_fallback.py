# 반응 GPT 폴백 + 프로바이더 무관 오케스트레이션(generate_reaction) 테스트
from __future__ import annotations

import pytest

from domain.simulation.adapters.gemini.reaction import generate_reaction
from domain.simulation.adapters.reaction_fallback import FallbackReactionEngine
from domain.simulation.contracts.schemas import AdInterpretation, Persona


def _persona() -> Persona:
    return Persona(
        persona_id="P-1",
        age=45,
        gender="M",
        region="서울",
        ocean={
            "openness": 0.0,
            "conscientiousness": 0.0,
            "extraversion": 0.0,
            "agreeableness": 0.0,
            "neuroticism": 0.0,
        },
    )


class _Engine:
    def __init__(self, version: str, result=None, exc: Exception | None = None) -> None:
        self.version = version
        self._result = result
        self._exc = exc
        self.calls = 0

    async def react(self, persona, ad):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._result


async def test_fallback_uses_primary_when_ok() -> None:
    primary = _Engine("gemini", result="R1")
    fallback = _Engine("gpt", result="R2")
    eng = FallbackReactionEngine([primary, fallback])
    out = await eng.react(_persona(), AdInterpretation(ad_id="A"))
    assert out == "R1"
    assert primary.calls == 1 and fallback.calls == 0  # 폴백 미호출
    assert eng.version == "gemini+gpt"


async def test_fallback_switches_on_primary_failure() -> None:
    primary = _Engine("gemini", exc=RuntimeError("503 overloaded"))
    fallback = _Engine("gpt", result="R2")
    eng = FallbackReactionEngine([primary, fallback])
    out = await eng.react(_persona(), AdInterpretation(ad_id="A"))
    assert out == "R2"
    assert primary.calls == 1 and fallback.calls == 1


async def test_fallback_raises_when_all_fail() -> None:
    primary = _Engine("gemini", exc=RuntimeError("503"))
    fallback = _Engine("gpt", exc=ValueError("boom"))
    eng = FallbackReactionEngine([primary, fallback])
    with pytest.raises(ValueError):  # 마지막 예외 전파
        await eng.react(_persona(), AdInterpretation(ad_id="A"))


def test_empty_engine_chain_rejected() -> None:
    # 엔진 0개 체인은 생성 단계에서 거부(폴백 대상 없음).
    with pytest.raises(ValueError, match="최소 1개"):
        FallbackReactionEngine([])


async def test_generate_reaction_is_provider_agnostic() -> None:
    """generate_reaction이 프롬프트를 구성하고 json_call 결과를 §3.5 반응으로 파싱한다."""

    async def json_call(prompt: str) -> dict:
        assert "[광고]" in prompt and "[나]" in prompt  # 공유 프롬프트가 구성됨
        return {
            "aisas": {
                "attention": True,
                "interest": True,
                "search": False,
                "action": False,
                "share": False,
            },
            "purchase_intent": 3,
            "trust": 4,
            "rejected": False,
            "utterance": "음 별로.",
        }

    out = await generate_reaction(json_call, _persona(), AdInterpretation(ad_id="A"))
    assert out.trust == 4
    assert out.purchase_intent == 3
    assert out.aisas.attention is True
    assert out.qa_passed is True
