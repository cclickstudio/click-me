# QA 검문소 — 규칙 기반(무콜) + LLM 기반(opt-in). AISAS 깔때기·광고무관·설정모순·앞뒤 불일치.
from __future__ import annotations

from domain.simulation.adapters.gemini._common import _DEFAULT_MODEL, _agen_json, _new_client
from domain.simulation.contracts.schemas import PersonaReaction


def _rule_check(reaction: PersonaReaction) -> tuple[bool, str | None]:
    """규칙 기반 일관성 검사(무콜) — AISAS 깔때기·필수 필드. LLM QA의 선검사로도 사용."""
    a = reaction.aisas
    if a.action and not (a.attention and a.interest):
        return False, "aisas_funnel_inconsistent"  # action엔 attention·interest 선행 필요
    if a.interest and not a.attention:
        return False, "aisas_funnel_inconsistent"
    if not (reaction.utterance or "").strip():
        return False, "empty_utterance"
    return True, None


class RuleQaGate:
    """규칙 기반 QA(LLM 콜 없음). 인터페이스 통일 위해 async."""

    async def check(
        self, reaction: PersonaReaction, attempt: int, *, persona=None, ad=None
    ) -> tuple[bool, str | None]:
        return _rule_check(reaction)


class GeminiQaGate:
    """규칙 선검사(무콜) 후 통과분만 LLM 일관성 검증(비동기, opt-in).

    콜 2배 방지: 규칙 탈락 시 LLM 호출 생략. 비동기라 fan-out에서 직렬화 없음.
    """

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = _new_client(api_key)
        self._model = model

    async def check(
        self, reaction: PersonaReaction, attempt: int, *, persona=None, ad=None
    ) -> tuple[bool, str | None]:
        ok, reason = _rule_check(reaction)
        if not ok:
            return ok, reason  # 규칙 탈락 → LLM 콜 생략
        income = getattr(persona, "socioeconomic", {}).get("income_bracket", "?")
        prompt = (
            "아래는 한 소비자가 광고에 보인 반응이다. 이 반응이 (a) 광고와 무관하지 않고 "
            "(b) 소비자 설정과 모순되지 않으며 (c) 앞뒤(구조화 값↔발화)가 일치하는지 판정하라.\n"
            'JSON만 출력: {"pass": true/false, "reason": "탈락 시 짧은 사유"}\n\n'
            f"[소비자] {getattr(persona, 'age', '?')}세 {getattr(persona, 'gender', '?')}, "
            f"소득 {income}\n"
            f"[광고] {getattr(ad, 'detected_message', '?')} "
            f"(타깃 {getattr(ad, 'detected_target', '?')})\n"
            f"[반응] 구매의도 {reaction.purchase_intent}/5, 신뢰 {reaction.trust}/5, "
            f"거부 {reaction.rejected}, 감정 {reaction.emotion_tag}, "
            f"인식메시지 '{reaction.perceived_message}', 발화 '{reaction.utterance}'"
        )
        try:
            data = await _agen_json(self._client, self._model, prompt)
        except Exception:
            return True, None  # LLM QA 실패 시 보수적 통과(런 유지) — 규칙은 이미 통과
        if data.get("pass", True):
            return True, None
        return False, f"llm_qa: {data.get('reason', 'inconsistent')}"
