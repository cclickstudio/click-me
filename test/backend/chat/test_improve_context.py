# improve 컨텍스트 빌더 순수 함수 검증 — DB 없이 요약 포맷·gen_data 조립을 고정
"""simulation_summary는 IMPROVE 유일 필수라 빈 문자열 금지(폴백 보장)를 함께 고정한다."""

from api.assistant.improve_context import (
    build_improve_gen_data,
    build_improvement_direction,
    build_sim_summary,
)

_FULL_AGG = {
    "purchase_intent": 3.2,
    "click_intent_rate": 0.45,
    "trust_avg": 3.5,
    "rejection_rate": 0.3,
}


def test_build_sim_summary_full_format():
    # 프론트 buildSimSummary(generator 페이지)와 동일 포맷 계약 고정.
    assert (
        build_sim_summary(_FULL_AGG, 10)
        == "표본 10명 · 구매의향 3.20/5 · 클릭의향 45% · 신뢰도 3.50/5 · 거부율 30%"
    )


def test_build_sim_summary_partial_none_skips():
    agg = {
        "purchase_intent": 4.0,
        "click_intent_rate": None,
        "trust_avg": None,
        "rejection_rate": None,
    }
    assert build_sim_summary(agg, None) == "구매의향 4.00/5"


def test_build_sim_summary_all_none_falls_back_to_title():
    assert build_sim_summary({}, None, "수분크림") == "수분크림 시뮬레이션 결과"
    assert build_sim_summary({}, None, None) == "광고 시뮬레이션 결과"


def test_build_improvement_direction_numbers_and_effect():
    actions = [
        {"action": "CTA를 키운다", "expected_effect": "클릭률 상승"},
        {"action": "가격 문구 축소"},
    ]
    assert (
        build_improvement_direction(actions) == "1. CTA를 키운다 — 클릭률 상승\n2. 가격 문구 축소"
    )


def test_build_improvement_direction_empty():
    assert build_improvement_direction([]) == ""


def _src(**over):
    base = {
        "ad_title": "수분크림",
        "ad_asset_url": "ads/abc.png",
        "sample_size": 10,
        "aggregate": dict(_FULL_AGG),
        "plain_summary": "AI 분석 텍스트",
        "ranked_actions": [{"action": "CTA 강화", "expected_effect": None}],
    }
    base.update(over)
    return base


def test_build_improve_gen_data_shape():
    data = build_improve_gen_data(_src(), fix_requests="가격 빼줘")
    assert data["mode"] == "improve"
    assert data["product_name"] == "수분크림"
    assert data["simulation_summary"].startswith("표본 10명")
    assert data["plain_summary"] == "AI 분석 텍스트"
    assert data["improvement_direction"] == "1. CTA 강화"
    assert data["existing_ad_s3_key"] == "ads/abc.png"
    assert data["fix_requests"] == "가격 빼줘"
    # 소스에 누끼 키가 없으면(생성한 광고로 시뮬한 게 아니면) None.
    assert data["product_cutout_s3_key"] is None


def test_build_improve_gen_data_carries_cutout_when_present():
    # 생성한 광고로 시뮬 → fetch_improve_source가 누끼 키를 실어주면 프리필에 그대로 전달.
    data = build_improve_gen_data(
        _src(product_cutout_s3_key="temp-product-images/gen-1-cutout.png")
    )
    assert data["product_cutout_s3_key"] == "temp-product-images/gen-1-cutout.png"


def test_build_improve_gen_data_filters_non_key_asset_url():
    # http URL·로컬경로는 S3 key 힌트로 못 쓴다 → None.
    assert (
        build_improve_gen_data(_src(ad_asset_url="https://x.com/a.png"))["existing_ad_s3_key"]
        is None
    )
    assert build_improve_gen_data(_src(ad_asset_url="C:\\tmp\\a.png"))["existing_ad_s3_key"] is None
    assert build_improve_gen_data(_src(ad_asset_url=None))["existing_ad_s3_key"] is None


def test_build_improve_gen_data_summary_never_empty():
    data = build_improve_gen_data(_src(aggregate={}, sample_size=None))
    assert data["simulation_summary"] == "수분크림 시뮬레이션 결과"
