# Mock 어댑터 — LLM 없이 결정적(seed 기반) 산출. 구조 검증·테스트·무API 데모용
#
# 실제 LLM 어댑터(vision·exposure·deliberation·ssr)는 tools/ 이전 후 별도 어댑터로 추가.
from __future__ import annotations

import random

from domain.simulation.contracts.enums import EmotionTag, RejectionReasonTag
from domain.simulation.contracts.schemas import (
    AdFeatures,
    AdInterpretation,
    Aisas,
    PanelSpec,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationRunRequest,
)
from domain.simulation.tools.reachability import pick_social_exposure

# 결정적 광고 특성 스텁 — 무콜 데모·테스트용. structured_analysis 와 ad_features 양쪽에 동일하게.
_MOCK_FEATURES = {
    "ad_credibility": 70,
    "ad_quality": 65,
    "price_mentioned": True,
    "original_price": 30000,
    "discounted_price": 19900,
    "brand_mentioned": True,
    "social_proof_strength": "medium",
}

# 결정적 시각 인벤토리 스텁(§4-a) — structured_analysis(JSONB)에만 담겨 반응 프롬프트로 흐른다.
_MOCK_VISUAL = {
    "primary_subject": "제품 패키지",
    "elements": ["제품샷", "할인 배지", "브랜드 로고", "CTA 버튼"],
    "first_impression": "큼지막한 할인 배지",
    "color_tone": "밝고 선명한 원색 톤",
}

_GENDERS = ("M", "F")
_REGIONS = ("서울", "경기", "부산", "대구", "광주")
_OCEAN_KEYS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


def _pick_exposure(persona: Persona, rng: random.Random) -> str:
    """노출맥락 — Meta 전용이므로 소셜피드만. 비소셜(TV 등)로는 폴백하지 않는다(모순 차단)."""
    candidates = persona.media_behavior.get("exposure_candidates") or []
    e = pick_social_exposure(candidates, rng)
    if e is None:
        return "sns_feed_evening"  # 소셜 후보 없을 때 기본값 — 비소셜 금지
    return f"{e['timeband']}·{e['place']}·{e['medium']}·{e['activity']}"


class MockAdInterpreter:
    """AdInterpreter 어댑터 —고정 해석 반환(선언 의도는 보지 않음, 앵커링 방지 §3.5-3)."""

    async def interpret(self, request: SimulationRunRequest) -> AdInterpretation:
        return AdInterpretation(
            ad_id=request.ad_id,
            structured_analysis={"mock": True, **_MOCK_FEATURES, "visual_elements": _MOCK_VISUAL},
            detected_industry="beverage",
            detected_objective="awareness",
            detected_target="20대",
            detected_message="신제품 출시",
            ad_features=AdFeatures(**_MOCK_FEATURES),
            intent_mismatch=False,
            model_version="mock-vision-0",
        )


class MockPanelProvider:
    """PanelProvider 어댑터 —seed 기반 결정적 페르소나 생성. 캐시 재사용은 추후."""

    async def get_or_build(self, spec: PanelSpec) -> tuple[str, list[Persona]]:
        rng = random.Random(spec.seed)
        personas: list[Persona] = []
        for i in range(spec.size):
            personas.append(
                Persona(
                    persona_id=f"P-{i:05d}",
                    age=rng.randint(20, 59),
                    gender=rng.choice(_GENDERS),
                    region=rng.choice(_REGIONS),
                    ocean={k: round(rng.random(), 2) for k in _OCEAN_KEYS},
                    media_behavior={"sns_hours": rng.randint(1, 6)},
                    consumption_values={"price_sensitivity": round(rng.random(), 2)},
                    profile_narrative="mock persona",
                )
            )
        return spec.version, personas


class MockReactionEngine:
    """ReactionEngine 어댑터 —페르소나별 결정적 반응(§3.5 형태)."""

    async def react(self, persona: Persona, ad: AdInterpretation) -> PersonaReaction:
        rng = random.Random(persona.persona_id)
        exposure = _pick_exposure(persona, rng)  # KISDI 노출맥락 후보에서 선택(반응마다 새로)
        attention = rng.random() > 0.2
        interest = attention and rng.random() > 0.3
        action = interest and rng.random() > 0.6
        rejected = rng.random() < 0.1
        return PersonaReaction(
            persona_id=persona.persona_id,
            exposure_context=exposure,
            aisas=Aisas(
                attention=attention,
                interest=interest,
                search=interest and rng.random() > 0.5,
                action=action,
                share=action and rng.random() > 0.7,
            ),
            drop_stage=None if action else "search",
            purchase_intent=rng.randint(1, 5),
            trust=rng.randint(1, 5),
            rejected=rejected,
            rejection_reason_tag=RejectionReasonTag.IRRELEVANT if rejected else None,
            emotion_tag=rng.choice(list(EmotionTag)),
            perceived_message=ad.detected_message,
            perceived_target=ad.detected_target,
            utterance="썸네일은 눈에 띄는데 뭘 사라는 건지 모르겠어요.",
            qa_passed=True,
        )


class MockRubricEvaluator:
    """RubricEvaluator 어댑터 —의도 정합 점수(선언 ↔ 감지) 결정적 산출(§3.5-3).

    선언 입력이 있는 차원만 채점. 선언==감지(유사)면 高, 다르면 低. 선언 미입력 차원은 생략.
    """

    async def evaluate(
        self, ad: AdInterpretation, request: SimulationRunRequest
    ) -> list[RubricScore]:
        # (정합 차원, 선언값, 감지값) — 선언 미입력이면 스킵.
        dims = (
            ("category_alignment", request.product_category, ad.detected_industry),
            ("objective_alignment", request.ad_objective, ad.detected_objective),
            ("message_alignment", request.ad_title, ad.detected_message),
        )
        scores: list[RubricScore] = []
        for dim, declared, detected in dims:
            if not declared:
                continue
            match = bool(detected) and declared.strip().lower() in str(detected).strip().lower()
            score = 90 if match else 40
            scores.append(
                RubricScore(
                    dimension=dim,
                    score=score,
                    evidence={
                        "declared": declared,
                        "detected": detected,
                        "note": "mock 정합" if match else "mock 불일치",
                    },
                )
            )
        return scores


class MockNarrator:
    """4-a 서사 생성(mock) — 속성을 결정적 한국어 문장으로 변환. LLM 없이 테스트·오프라인용."""

    version = "mock-narrator-0"

    def narrate(self, persona: Persona) -> str:
        top = max(persona.ocean, key=persona.ocean.get) if persona.ocean else "openness"
        medium = persona.media_behavior.get("primary_medium", "미디어")
        minutes = persona.media_behavior.get("daily_media_minutes", "?")
        se = persona.socioeconomic
        edu = se.get("education")
        income = se.get("income_bracket")
        se_phrase = f" {edu}, 월소득 {income}." if edu and income else ""
        return (
            f"{persona.age}세 {persona.gender} · {persona.region}.{se_phrase} "
            f"성격은 {top}이(가) 두드러지고, 주 이용 미디어는 {medium}(하루 약 {minutes}분)."
        )


class MockQaGate:
    """QA 검문소(mock) — 결정적으로 일부 첫 시도를 탈락시켜 재시도 루프를 검증.

    실제 QA(광고 무관·설정 모순·앞뒤 불일치 판정)는 추후 어댑터로 교체.
    persona_id 기반 결정적 판정 → 약 20%가 첫 시도 탈락, 재생성(재시도) 시 통과로 간주.
    """

    async def check(
        self, reaction: PersonaReaction, attempt: int, *, persona=None, ad=None
    ) -> tuple[bool, str | None]:
        if attempt < 2 and sum(map(ord, reaction.persona_id)) % 5 == 0:
            return False, "mock_qa_inconsistent"
        return True, None
