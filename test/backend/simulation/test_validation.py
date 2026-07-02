# P9 검증 데모 단위 테스트 — directional_verdict 순수 판정(LLM 없음)
from __future__ import annotations

from domain.simulation.validation import directional_verdict


def _band(age_mid: int, *, rejection: float, purchase: float, click: float = 0.0) -> dict:
    return {
        "age_mid": age_mid,
        "rejection_rate": rejection,
        "purchase_intent": purchase,
        "click_intent_rate": click,
    }


def test_young_target_pattern_passes() -> None:
    # 젊은 타깃 광고: 연령↑ → 거부율↑·구매의도↓ → 가설 통과.
    by_band = [
        _band(25, rejection=0.1, purchase=4.2, click=0.4),
        _band(35, rejection=0.3, purchase=3.5, click=0.3),
        _band(45, rejection=0.5, purchase=2.8, click=0.2),
        _band(55, rejection=0.7, purchase=2.0, click=0.1),
    ]
    v = directional_verdict(by_band)
    assert v["rejection_rises_with_age"] and v["purchase_falls_with_age"]
    assert v["directional_pass"] is True


def test_flat_or_reverse_pattern_fails() -> None:
    # 연령과 무관(거부율 동일·구매의도 상승) → 가설 미통과.
    by_band = [
        _band(25, rejection=0.4, purchase=2.0),
        _band(45, rejection=0.4, purchase=3.0),
        _band(65, rejection=0.4, purchase=4.0),
    ]
    v = directional_verdict(by_band)
    assert v["directional_pass"] is False
