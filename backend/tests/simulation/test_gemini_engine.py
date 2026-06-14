# 실 LLM 어댑터(P4)의 무콜 순수 로직 테스트 — RuleQaGate·JSON 파싱 (Gemini API 호출 없음)
from __future__ import annotations

from domain.simulation.adapters.gemini_engine import RuleQaGate, _parse_json
from domain.simulation.contracts.schemas import Aisas, PersonaReaction


def _reaction(**kw: object) -> PersonaReaction:
    base = {
        "persona_id": "P-1",
        "aisas": Aisas(attention=True, interest=True, action=True),
        "purchase_intent": 3,
        "trust": 3,
        "utterance": "괜찮아 보여요.",
    }
    base.update(kw)
    return PersonaReaction(**base)


async def test_qa_passes_consistent_funnel() -> None:
    ok, reason = await RuleQaGate().check(_reaction(), attempt=1)
    assert ok and reason is None


async def test_qa_fails_when_action_without_attention() -> None:
    # action=True인데 attention=False → 깔때기 모순.
    r = _reaction(aisas=Aisas(attention=False, interest=False, action=True))
    ok, reason = await RuleQaGate().check(r, attempt=1)
    assert not ok and reason == "aisas_funnel_inconsistent"


async def test_qa_fails_on_empty_utterance() -> None:
    ok, reason = await RuleQaGate().check(_reaction(utterance="  "), attempt=1)
    assert not ok and reason == "empty_utterance"


async def test_qa_accepts_persona_ad_kwargs() -> None:
    # 확장된 인터페이스(persona·ad) — 규칙 QA는 무시하고 동일 판정.
    ok, reason = await RuleQaGate().check(_reaction(), attempt=0, persona=object(), ad=object())
    assert ok and reason is None


def test_parse_json_strips_code_fence() -> None:
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('{"b": 2}') == {"b": 2}
