# 집계 엔진 단위 테스트 — 부트스트랩 CI·variance_warning·QA 필터 검증
from __future__ import annotations

from domain.simulation.contracts.schemas import Aisas, PersonaReaction
from domain.simulation.tools.aggregation.aggregator import BasicAggregator


def _reaction(
    pid: str,
    *,
    action: bool,
    purchase: int,
    trust: int = 3,
    rejected: bool = False,
    qa: bool = True,
    weight: float = 1.0,
) -> PersonaReaction:
    return PersonaReaction(
        persona_id=pid,
        aisas=Aisas(attention=True, action=action),
        purchase_intent=purchase,
        trust=trust,
        rejected=rejected,
        qa_passed=qa,
        weight=weight,
    )


def test_empty_sample_warns_and_zeros() -> None:
    agg = BasicAggregator().aggregate([])
    assert agg.click_intent_rate == 0.0
    assert agg.variance_warning is True
    assert agg.payload["qa_passed_count"] == 0


def test_qa_failed_excluded_from_aggregation() -> None:
    reactions = [
        _reaction("P-1", action=True, purchase=5, qa=True),
        _reaction("P-2", action=True, purchase=1, qa=False),  # 제외
    ]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.payload["qa_passed_count"] == 1
    assert agg.click_intent_rate == 1.0  # 통과분(P-1)만 집계


def test_ci_brackets_point_estimate() -> None:
    # 절반만 action=True → click_rate≈0.5, CI가 점추정을 감싼다.
    reactions = [_reaction(f"P-{i}", action=(i % 2 == 0), purchase=(i % 5) + 1) for i in range(40)]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.ci_low <= agg.click_intent_rate <= agg.ci_high
    assert agg.ci_low < agg.ci_high  # 표본 변동이 있으면 폭이 0보다 큼
    assert agg.payload["ci_method"] == "weighted_bootstrap"


def test_low_purchase_variance_triggers_warning() -> None:
    # 전원 동일 구매의도(3) → 표준편차 0 → 응답 집중 경고.
    reactions = [_reaction(f"P-{i}", action=(i % 2 == 0), purchase=3) for i in range(30)]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.variance_warning is True
    assert agg.payload["purchase_std"] == 0.0


def test_spread_purchase_no_warning() -> None:
    # 1~5 고르게 분산 → 표준편차 충분 → 경고 없음.
    reactions = [_reaction(f"P-{i}", action=True, purchase=(i % 5) + 1) for i in range(50)]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.variance_warning is False


def test_uniform_weights_match_unweighted_and_effective_n_equals_n() -> None:
    # 균일 가중(self-weighting) → 가중 평균 = 단순 평균, 유효표본수 = n.
    reactions = [_reaction(f"P-{i}", action=(i < 10), purchase=3) for i in range(40)]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.click_intent_rate == 0.25  # 10/40
    assert agg.effective_n == 40.0


def test_nonuniform_weights_shift_estimate_and_reduce_effective_n() -> None:
    # action=True 1명에 큰 가중, action=False 3명에 작은 가중 → 가중 클릭률↑, 유효표본 < 4.
    reactions = [
        _reaction("P-1", action=True, purchase=5, weight=7.0),
        _reaction("P-2", action=False, purchase=1, weight=1.0),
        _reaction("P-3", action=False, purchase=1, weight=1.0),
        _reaction("P-4", action=False, purchase=1, weight=1.0),
    ]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.click_intent_rate == 0.7  # 7/(7+1+1+1)
    assert agg.effective_n < 4.0  # Kish: 가중 편차로 유효표본 감소
    assert agg.payload["weight_sum"] == 10.0
