# 4-b 반응 어댑터 — 페르소나가 광고에 '한 사람처럼' 반응(§3.5 구조화 JSON 강제, 비동기).
#
# 다양성 보존 위해 temperature 높게(동질화 방지). 숫자(집계)는 코드, 반응 '문장'만 LLM.
from __future__ import annotations

import random

from domain.simulation.adapters.gemini._common import (
    _DEFAULT_MODEL,
    _agen_json,
    _enum_values,
    _new_client,
)
from domain.simulation.contracts.enums import (
    AisasStage,
    DropReasonTag,
    EmotionTag,
    RejectionReasonTag,
)
from domain.simulation.contracts.schemas import AdInterpretation, Aisas, PersonaReaction
from domain.simulation.tools.reachability import pick_social_exposure


def _pick_exposure(persona, rng: random.Random) -> str | None:
    # Meta 전용 — 노출맥락은 항상 소셜피드. 비소셜(TV·신문 등)로는 절대 폴백하지 않는다(모순 차단).
    cands = persona.media_behavior.get("exposure_candidates") or []
    e = pick_social_exposure(cands, rng)
    if e is None:
        # 소셜 후보가 없으면(구버전 패널 등) 일반 소셜피드 기본값 — TV 등 비소셜 금지.
        return "저녁·집·스마트폰/휴대폰·SNS"
    return f"{e['timeband']}·{e['place']}·{e['medium']}·{e['activity']}"


def _ad_feature_lines(ad: AdInterpretation, income: str) -> str:
    """광고 특성을 반응 힌트 줄로 — 가격은 월소득과 나란히 둬 적합도를 LLM이 판단(공식 없음)."""
    f = ad.ad_features
    lines: list[str] = []
    if f.price_mentioned and (f.original_price or f.discounted_price):
        if f.discounted_price and f.original_price:
            price = f"정가 {f.original_price:,}원 → 할인가 {f.discounted_price:,}원"
        else:
            price = f"{(f.discounted_price or f.original_price):,}원"
        lines.append(f"- 가격: {price} (내 월소득 {income} 기준으로 비싼지/적당한지 판단)")
    if f.brand_mentioned:
        lines.append("- 브랜드 언급: 있음")
    if f.social_proof_strength and f.social_proof_strength != "none":
        lines.append(f"- 사회적 증거(후기·인기): {f.social_proof_strength}")
    return ("\n" + "\n".join(lines)) if lines else ""


class GeminiReactionEngine:
    """4-b 반응 — §3.5 구조화 JSON 강제(비동기). temperature↑로 페르소나 간 응답 다양성 보존."""

    def __init__(
        self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL, temperature: float = 1.0
    ) -> None:
        self._client = _new_client(api_key)
        self._model = model
        self.version = model
        self._temperature = temperature

    def _prompt(self, persona, ad: AdInterpretation, exposure: str | None) -> str:
        income = persona.socioeconomic.get("income_bracket", "?")
        edu = persona.socioeconomic.get("education", "?")
        values = [k for k, v in persona.consumption_values.items() if v]
        return (
            "당신은 아래 한국 소비자 '본인'입니다. 이 사람의 성격·형편·미디어 습관에 충실하게, "
            "주어진 광고에 솔직하게 반응하세요. 교과서적 정답이 아니라 이 사람의 실제 반응을.\n\n"
            f"[나]\n- {persona.age}세 {persona.gender}, {persona.region}\n"
            f"- 학력 {edu}, 월소득 {income}\n"
            f"- OCEAN(표준화, 양수=평균이상): {persona.ocean}\n"
            f"- 주 이용 미디어: {persona.media_behavior.get('primary_medium', '?')}\n"
            f"- 중시 소비가치: {values}\n"
            f"- 서사: {persona.profile_narrative or '(없음)'}\n"
            f"- 지금 노출 맥락: {exposure or '일반'}\n\n"
            f"[광고]\n- 업종: {ad.detected_industry}\n- 메시지: {ad.detected_message}\n"
            f"- 추정 타깃: {ad.detected_target}{_ad_feature_lines(ad, income)}\n\n"
            "[출력 — 아래 JSON만, 설명·코드펜스 없이]\n"
            "{\n"
            '  "aisas": {"attention": bool, "interest": bool, "search": bool, '
            '"action": bool, "share": bool},\n'
            f'  "drop_stage": null 또는 [{_enum_values(AisasStage)}] 중 이탈 단계,\n'
            f'  "drop_reason_tag": null 또는 [{_enum_values(DropReasonTag)}] 중 하나,\n'
            '  "purchase_intent": 1~5 정수, "trust": 1~5 정수, "rejected": bool,\n'
            f'  "rejection_reason_tag": null 또는 [{_enum_values(RejectionReasonTag)}] 중 하나,\n'
            f'  "emotion_tag": [{_enum_values(EmotionTag)}] 중 하나,\n'
            '  "perceived_message": "내가 이해한 메시지", "perceived_target": "내가 느낀 타깃",\n'
            '  "utterance": "한 문장 솔직한 반응"\n'
            "}\n"
            "주의: AISAS는 깔때기 — action=true면 attention·interest도 true여야 한다. "
            "태그는 반드시 제시된 값에서만 고른다(새 값 금지)."
        )

    async def react(self, persona, ad: AdInterpretation) -> PersonaReaction:
        rng = random.Random(persona.persona_id)
        exposure = _pick_exposure(persona, rng)
        data = await _agen_json(
            self._client,
            self._model,
            self._prompt(persona, ad, exposure),
            temperature=self._temperature,
        )
        return PersonaReaction(
            persona_id=persona.persona_id,
            exposure_context=exposure,
            aisas=Aisas(**data.get("aisas", {})),
            drop_stage=data.get("drop_stage"),
            drop_reason_tag=data.get("drop_reason_tag"),
            purchase_intent=int(data["purchase_intent"]),
            trust=int(data["trust"]),
            rejected=bool(data.get("rejected", False)),
            rejection_reason_tag=data.get("rejection_reason_tag"),
            emotion_tag=data.get("emotion_tag", EmotionTag.INDIFFERENCE),
            perceived_message=data.get("perceived_message"),
            perceived_target=data.get("perceived_target"),
            utterance=data.get("utterance"),
            qa_passed=True,  # QA 게이트가 별도 판정
        )
