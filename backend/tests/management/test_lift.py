"""🅰 오가닉↔광고 리프트 계산·비교 서비스 테스트."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from domain.management.comparison.lift import compute_lift
from domain.management.comparison.schemas import LiftVerdict, PostInsights, PostType


def _post(post_type: PostType, reach: int, impressions: int, **kw: int) -> PostInsights:
    return PostInsights(
        post_id="p1",
        post_type=post_type,
        as_of=datetime.now(UTC),
        reach=reach,
        impressions=impressions,
        engagement=kw.get("engagement", 0),
        clicks=kw.get("clicks", 0),
        spend_krw=kw.get("spend_krw", 0),
    )


def test_lift_pass_when_reach_x3_or_more():
    organic = _post(PostType.ORGANIC, 3000, 4500)
    paid = _post(PostType.PAID, 22000, 40000, clicks=1900, spend_krw=84000)
    r = compute_lift(organic, paid)
    assert r.verdict == LiftVerdict.PASS
    assert r.reach_lift_abs == 19000
    assert r.reach_lift_ratio == pytest.approx(22000 / 3000, abs=0.01)
    assert r.impressions_lift_abs == 35500


def test_lift_caution_between_1_5_and_3():
    r = compute_lift(_post(PostType.ORGANIC, 4000, 5000), _post(PostType.PAID, 9000, 11000))
    assert r.verdict == LiftVerdict.CAUTION


def test_lift_fail_below_1_5():
    # 2500/2000 = ×1.25 < 1.5 → 미달
    r = compute_lift(_post(PostType.ORGANIC, 2000, 3000), _post(PostType.PAID, 2500, 3200))
    assert r.verdict == LiftVerdict.FAIL


def test_lift_handles_zero_organic_reach():
    # 오가닉 도달 0 → 분모 1 보수 처리 → 0division 없이 PASS
    r = compute_lift(_post(PostType.ORGANIC, 0, 0), _post(PostType.PAID, 5000, 8000))
    assert r.verdict == LiftVerdict.PASS
    assert r.reach_lift_abs == 5000


def test_comparison_service_with_mock_and_fake_ad():
    from domain.management.adapters.mock import MockOrganicReader
    from domain.management.comparison.service.comparison_service import ComparisonService
    from domain.management.contracts.schemas import MetricsSnapshot

    class _FakeAd:
        async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot:
            return MetricsSnapshot(
                campaign_id=campaign_id,
                as_of=datetime.now(UTC),
                impressions=40000,
                clicks=1900,
                inline_link_clicks=1700,
                spend_krw=84000,
                cum_impressions=40000,
                cum_reach=22000,
                frequency=1.8,
                ctr=0.047,
                cpm_krw=2100,
                cpc_krw=44,
            )

    async def _run():
        svc = ComparisonService(MockOrganicReader(), _FakeAd())
        return await svc.compare("media123", "camp1", datetime.now(UTC) - timedelta(days=7))

    res = asyncio.run(_run())
    assert res.paid.reach == 22000
    assert res.paid.post_type == PostType.PAID
    assert res.organic.post_type == PostType.ORGANIC
    # 오가닉 mock 도달 2000~4000 → 광고 22000 대비 ×5.5~×11 → PASS
    assert res.verdict == LiftVerdict.PASS
