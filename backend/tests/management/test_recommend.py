"""🅰 리프트 판정 → 추천 액션 신호 변환 테스트."""

from datetime import UTC, datetime

from domain.management.comparison.lift import compute_lift
from domain.management.comparison.recommend import recommend_action
from domain.management.comparison.schemas import (
    LiftVerdict,
    PostInsights,
    PostType,
    RecommendedAction,
)


def _post(post_type: PostType, reach: int, impressions: int) -> PostInsights:
    return PostInsights(
        post_id="p1",
        post_type=post_type,
        as_of=datetime.now(UTC),
        reach=reach,
        impressions=impressions,
        engagement=0,
        clicks=0,
        spend_krw=0,
    )


def test_pass_recommends_scale_up_with_increase_budget_hint():
    lift = compute_lift(_post(PostType.ORGANIC, 3000, 4500), _post(PostType.PAID, 22000, 40000))
    rec = recommend_action(lift)
    assert lift.verdict == LiftVerdict.PASS
    assert rec.recommended_action == RecommendedAction.SCALE_UP
    assert rec.suggested_action_type == "INCREASE_BUDGET"
    assert rec.post_id == lift.post_id
    assert rec.reach_lift_ratio == lift.reach_lift_ratio


def test_caution_recommends_hold_without_action_hint():
    lift = compute_lift(_post(PostType.ORGANIC, 4000, 5000), _post(PostType.PAID, 9000, 11000))
    rec = recommend_action(lift)
    assert lift.verdict == LiftVerdict.CAUTION
    assert rec.recommended_action == RecommendedAction.HOLD
    assert rec.suggested_action_type == ""


def test_fail_recommends_pause_with_pause_campaign_hint():
    lift = compute_lift(_post(PostType.ORGANIC, 2000, 3000), _post(PostType.PAID, 2500, 3200))
    rec = recommend_action(lift)
    assert lift.verdict == LiftVerdict.FAIL
    assert rec.recommended_action == RecommendedAction.PAUSE
    assert rec.suggested_action_type == "PAUSE_CAMPAIGN"


def test_service_compare_and_recommend_bundles_lift_and_recommendation():
    import asyncio
    from datetime import timedelta

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
        return await svc.compare_and_recommend(
            "media123", "camp1", datetime.now(UTC) - timedelta(days=7)
        )

    report = asyncio.run(_run())
    # 묶음: 상세 리프트 + 권고가 같은 산출물에 함께
    assert report.lift.verdict == LiftVerdict.PASS
    assert report.recommendation.recommended_action == RecommendedAction.SCALE_UP
    assert report.recommendation.suggested_action_type == "INCREASE_BUDGET"
    # 일관성: 권고의 post_id·ratio는 리프트와 동일
    assert report.recommendation.post_id == report.lift.post_id
    assert report.recommendation.reach_lift_ratio == report.lift.reach_lift_ratio
