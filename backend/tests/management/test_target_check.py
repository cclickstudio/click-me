"""목표 대비 성과 미달 판정 — 실 캠페인 ROAS vs 고객 목표(결정 3)."""

from datetime import UTC, datetime

from api.routers.management import _real_summary
from domain.management.contracts.schemas import MetricsSnapshot
from domain.management.target_check import is_target_missed


def test_is_target_missed_below_threshold():
    assert is_target_missed(1.0, 2.0) is True  # 1.0 < 2.0×0.7=1.4


def test_is_target_missed_within_tolerance():
    assert is_target_missed(1.5, 2.0) is False  # 1.5 ≥ 1.4 → 허용


def test_is_target_missed_none_inputs():
    assert is_target_missed(None, 2.0) is False  # ROAS 미측정 → 판정 불가
    assert is_target_missed(1.0, None) is False  # 목표 미입력 → 판정 안 함


def _snap(roas: float | None) -> MetricsSnapshot:
    return MetricsSnapshot(
        campaign_id="c1",
        as_of=datetime(2026, 6, 20, tzinfo=UTC),
        impressions=1000,
        clicks=100,
        inline_link_clicks=80,
        spend_krw=200_000,
        cum_impressions=1000,
        cum_reach=900,
        frequency=1.1,
        ctr=0.1,
        cpm_krw=2000,
        cpc_krw=2000,
        conversions=30,
        cvr=None,
        roas=roas,
    )


def test_real_summary_flags_target_missed():
    s = _real_summary(_snap(1.0), 200_000, target_roas=2.0)
    assert s["target_roas"] == 2.0
    assert s["target_missed"] is True


def test_real_summary_no_target_no_flag():
    s = _real_summary(_snap(1.0), 200_000)
    assert s["target_roas"] is None
    assert s["target_missed"] is False


def test_real_summary_target_uses_estimated_roas():
    # 추정 ROAS(=30×10,000/200,000=1.5)도 목표 판정에 쓰인다. 1.5 < 3.0×0.7=2.1 → 미달.
    s = _real_summary(_snap(None), 200_000, conversion_value_krw=10_000, target_roas=3.0)
    assert s["roas_estimated"] is True
    assert s["target_missed"] is True
