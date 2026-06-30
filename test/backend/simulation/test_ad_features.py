# 광고 특성(AdFeatures) 파싱·Mock 산출·반응 프롬프트 연동 테스트 (무API, 순수 로직)
from __future__ import annotations

from domain.simulation.adapters.gemini.reaction import _ad_feature_lines
from domain.simulation.contracts.schemas import AdFeatures, AdInterpretation


def test_ad_features_defaults() -> None:
    f = AdFeatures()
    assert f.ad_credibility is None and f.ad_quality is None
    assert f.price_mentioned is False and f.brand_mentioned is False
    assert f.social_proof_strength is None


def test_ad_features_partial_dict() -> None:
    # LLM JSON 중 일부 키만 와도 나머지는 기본값으로 채워진다.
    f = AdFeatures(**{"ad_quality": 80, "price_mentioned": True})
    assert f.ad_quality == 80 and f.price_mentioned is True
    assert f.ad_credibility is None


def test_reaction_feature_lines_include_price_with_income() -> None:
    ad = AdInterpretation(
        ad_id="AD-1",
        ad_features=AdFeatures(
            price_mentioned=True,
            original_price=30000,
            discounted_price=19900,
            brand_mentioned=True,
            social_proof_strength="high",
        ),
    )
    lines = _ad_feature_lines(ad, income="300만원대")
    assert "정가 30,000원 → 할인가 19,900원" in lines
    assert "300만원대" in lines  # 소득과 가격을 나란히 둬 적합도 판단 힌트
    assert "사회적 증거" in lines and "high" in lines


def test_reaction_feature_lines_empty_when_no_features() -> None:
    ad = AdInterpretation(ad_id="AD-1")  # 기본 AdFeatures(전부 미언급)
    assert _ad_feature_lines(ad, income="?") == ""
