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
    interest: bool | None = None,
) -> PersonaReaction:
    # interest 미지정 시 깔때기 정합(action=True면 interest=True) 기본값.
    return PersonaReaction(
        persona_id=pid,
        aisas=Aisas(
            attention=True, interest=action if interest is None else interest, action=action
        ),
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


def test_all_qa_failed_returns_zeroed_no_sample_path() -> None:
    # 표본은 있으나 전원 QA 실패 → 빈 표본과 동일한 무표본 경로.
    reactions = [_reaction(f"P-{i}", action=True, purchase=5, qa=False) for i in range(5)]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.payload["qa_passed_count"] == 0
    assert agg.payload["note"] == "QA 통과 표본 없음"
    assert agg.click_intent_rate == 0.0
    assert agg.ci_low == 0.0 and agg.ci_high == 0.0
    assert agg.effective_n == 0.0
    assert agg.variance_warning is True


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


def test_effective_n_kish_exact_value() -> None:
    # Kish: (Σw)²/Σ(w²). weight=[3,1,1,1] → 36/12 = 3.0 (n=4 보다 작음).
    reactions = [
        _reaction("P-1", action=True, purchase=5, weight=3.0),
        _reaction("P-2", action=False, purchase=1, weight=1.0),
        _reaction("P-3", action=False, purchase=1, weight=1.0),
        _reaction("P-4", action=False, purchase=1, weight=1.0),
    ]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.effective_n == 3.0  # 36/12
    # 균일 가중이면 effective_n == n 임을 같은 공식으로 교차확인.
    uniform = [_reaction(f"U-{i}", action=True, purchase=3, weight=2.0) for i in range(5)]
    assert BasicAggregator().aggregate(uniform).effective_n == 5.0  # (10)²/(5·4)=100/20


def test_single_sample_no_exception() -> None:
    # 단일 표본(n=1) → 부트스트랩·Kish 모두 예외 없이 점값 반환.
    agg = BasicAggregator().aggregate([_reaction("P-1", action=True, purchase=4, weight=1.0)])
    assert agg.click_intent_rate == 1.0
    assert agg.ci_low == 1.0 and agg.ci_high == 1.0  # 단일 표본은 재추출해도 동일
    assert agg.effective_n == 1.0
    assert agg.variance_warning is True  # 단일 값 → 표준편차 0


def test_interest_conditional_rate_and_gap() -> None:
    # 20명 중 관심 통과 8명, 그중 클릭 4명 → 전체 0.2, 관심층 조건부 0.5.
    reactions = [
        _reaction(f"P-{i}", action=(i < 4), purchase=(i % 5) + 1, interest=(i < 8))
        for i in range(20)
    ]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.click_intent_rate == 0.2  # 4/20 — 기존 KPI 무변경
    ic = agg.payload["interest_conditional"]
    assert ic["click_intent_rate"] == 0.5  # 4/8
    assert ic["interest_passed_n"] == 8
    assert ic["ci_low"] <= 0.5 <= ic["ci_high"]
    assert ic["low_sample"] is False  # 균일 가중 유효표본 8 ≥ 5


def test_interest_conditional_omitted_when_no_interest() -> None:
    # 관심 통과 0명 → 키 자체 생략(0.0 채움 금지).
    reactions = [_reaction(f"P-{i}", action=False, purchase=3, interest=False) for i in range(10)]
    agg = BasicAggregator().aggregate(reactions)
    assert "interest_conditional" not in agg.payload


def test_interest_conditional_low_sample_flag() -> None:
    # 관심 통과 3명(유효표본 3 < 5) → low_sample 플래그.
    reactions = [
        _reaction(f"P-{i}", action=(i < 2), purchase=(i % 5) + 1, interest=(i < 3))
        for i in range(30)
    ]
    agg = BasicAggregator().aggregate(reactions)
    ic = agg.payload["interest_conditional"]
    assert ic["interest_passed_n"] == 3
    assert ic["low_sample"] is True


def test_interest_conditional_weighted() -> None:
    # 관심층 내 가중 반영 — 클릭 1명 w=3, 비클릭 1명 w=1 → 3/4.
    reactions = [
        _reaction("P-1", action=True, purchase=5, weight=3.0),
        _reaction("P-2", action=False, purchase=1, weight=1.0, interest=True),
        _reaction("P-3", action=False, purchase=2, weight=5.0, interest=False),  # 분모 제외
    ]
    agg = BasicAggregator().aggregate(reactions)
    ic = agg.payload["interest_conditional"]
    assert ic["click_intent_rate"] == 0.75
    assert ic["interest_passed_n"] == 2


def test_interest_conditional_excludes_qa_failed() -> None:
    # QA 실패 반응은 관심층 분모에서도 제외.
    reactions = [
        _reaction("P-1", action=True, purchase=5),
        _reaction("P-2", action=False, purchase=1, interest=True, qa=False),
    ]
    agg = BasicAggregator().aggregate(reactions)
    ic = agg.payload["interest_conditional"]
    assert ic["interest_passed_n"] == 1
    assert ic["click_intent_rate"] == 1.0


def test_extreme_weight_deviation_collapses_effective_n() -> None:
    # 한 명에 극단 가중(1000) + 나머지 1 → 유효표본이 1 근처로 붕괴(effective_n ≪ n).
    reactions = [_reaction("P-0", action=True, purchase=5, weight=1000.0)]
    reactions += [_reaction(f"P-{i}", action=False, purchase=1, weight=1.0) for i in range(1, 20)]
    agg = BasicAggregator().aggregate(reactions)
    assert agg.effective_n < 2.0  # n=20 인데 유효표본은 1 근처
    assert agg.click_intent_rate > 0.9  # 큰 가중 표본(action=True)이 지배
