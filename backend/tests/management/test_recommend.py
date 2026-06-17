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
