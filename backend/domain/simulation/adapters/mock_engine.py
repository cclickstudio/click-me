# Mock 어댑터 — LLM 없이 결정적(seed 기반) 산출. 구조 검증·테스트·무API 데모용
#
# 실제 LLM 어댑터(vision·exposure·deliberation·ssr)는 tools/ 이전 후 별도 어댑터로 추가.
from __future__ import annotations

import random

from domain.simulation.contracts.enums import EmotionTag, RejectionReasonTag
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    PanelSpec,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationRunRequest,
)

_GENDERS = ("M", "F")
_REGIONS = ("서울", "경기", "부산", "대구", "광주")
_OCEAN_KEYS = ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism")


class MockAdInterpreter:
    """AdInterpreter 어댑터 —고정 해석 반환."""

    async def interpret(self, request: SimulationRunRequest) -> AdInterpretation:
        return AdInterpretation(
            ad_id=request.ad_id,
            structured_analysis={"mock": True},
            detected_industry="beverage",
            detected_target="20대",
            detected_message="신제품 출시",
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
        attention = rng.random() > 0.2
        interest = attention and rng.random() > 0.3
        action = interest and rng.random() > 0.6
        rejected = rng.random() < 0.1
        return PersonaReaction(
            persona_id=persona.persona_id,
            exposure_context="sns_feed_evening",
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
    """RubricEvaluator 어댑터 —차원별 점수(숫자) 결정적 산출."""

    async def evaluate(self, ad: AdInterpretation) -> list[RubricScore]:
        rng = random.Random(ad.ad_id)
        dimensions = ("clarity", "relevance", "trust", "creativity", "cta_strength")
        return [
            RubricScore(dimension=d, score=rng.randint(40, 90), evidence={"mock": True})
            for d in dimensions
        ]
