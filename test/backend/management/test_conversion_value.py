"""통계가치 기반 추정 ROAS — 측정 매출 없는 전환의 ROAS 환산·표기 검증."""

from datetime import UTC, datetime

from api.routers.management import _real_summary
from domain.management.contracts.schemas import MetricsSnapshot
from domain.management.conversion_value import estimate_roas


def test_estimate_roas_basic():
    # 리드 30건 × ₩10,000 ÷ ₩200,000 = 1.5
    assert estimate_roas(30, 10_000, 200_000) == 1.5


def test_estimate_roas_none_when_missing():
    assert estimate_roas(0, 10_000, 200_000) is None  # 전환 0
    assert estimate_roas(30, None, 200_000) is None  # 가치 미입력
    assert estimate_roas(30, 10_000, 0) is None  # 지출 0


def _snap(conversions: int | None, roas: float | None, spend: int = 200_000) -> MetricsSnapshot:
    return MetricsSnapshot(
        campaign_id="c1",
        as_of=datetime(2026, 6, 20, tzinfo=UTC),
        impressions=1000,
        clicks=100,
        inline_link_clicks=80,
        spend_krw=spend,
        cum_impressions=1000,
        cum_reach=900,
        frequency=1.1,
        ctr=0.1,
        cpm_krw=2000,
        cpc_krw=2000,
        conversions=conversions,
        cvr=None,
        roas=roas,
    )


def test_real_summary_overlays_estimated_roas_when_value_given():
    s = _real_summary(_snap(30, None), 200_000, conversion_value_krw=10_000)
    assert s["roas"] == 1.5
    assert s["roas_estimated"] is True


def test_real_summary_keeps_measured_roas_untouched():
    # 구매 실측 ROAS가 있으면 추정으로 덮지 않는다.
    s = _real_summary(_snap(9, 5.0), 200_000, conversion_value_krw=10_000)
    assert s["roas"] == 5.0
    assert s["roas_estimated"] is False


def test_real_summary_no_value_no_estimate():
    s = _real_summary(_snap(30, None), 200_000)
    assert s["roas"] is None
    assert s["roas_estimated"] is False
