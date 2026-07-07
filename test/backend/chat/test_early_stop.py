# 개선루프 조기 종료 골든 — assess_early_stop 규칙 + result_callback 조기종료 흐름
"""KPI 등급 기반 조기 종료 판정(오조기종료 방지)과 result_callback 통합을 고정한다.

판정은 loop_count 누적이 아니라 시뮬 KPI 등급으로 하므로, 인메모리 loop_count 초기화의
영향을 받지 않는다(서버 재시작 회피). 규칙은 loop_state.assess_early_stop 참고.
"""

from domain.chat import result_callback
from domain.chat.loop_state import assess_early_stop, get_loop_state, reset_loop_state
from domain.simulation.contracts.schemas import ObjectiveFit, SimulationAggregate


def _fit(grade: str = "높음", *, low_confidence: bool = False, score: int = 80) -> ObjectiveFit:
    return ObjectiveFit(
        objective="클릭 유도",
        matched_goal="click",
        score=score,
        grade=grade,
        rationale="테스트용",
        low_confidence=low_confidence,
    )


def _agg(
    *,
    click_intent_rate: float = 0.3,
    purchase_intent: float = 3.0,
    trust_avg: float = 3.0,
    rejection_rate: float = 0.3,
    variance_warning: bool = False,
    effective_n: float = 30.0,
) -> SimulationAggregate:
    return SimulationAggregate(
        click_intent_rate=click_intent_rate,
        ci_low=max(0.0, click_intent_rate - 0.05),
        ci_high=min(1.0, click_intent_rate + 0.05),
        purchase_intent=purchase_intent,
        trust_avg=trust_avg,
        rejection_rate=rejection_rate,
        variance_warning=variance_warning,
        effective_n=effective_n,
    )


# ── 종료(True) 케이스 ──


def test_stop_when_grade_high_and_enough_sample():
    stop, reason = assess_early_stop(_fit(grade="높음"), _agg(effective_n=20))
    assert stop is True
    assert reason  # 사유 문자열 존재


def test_stop_when_kpi_thresholds_met():
    # 등급이 '보통'이어도 KPI 임계(클릭>0.6·구매>3.5·거부<0.2) 충족이면 종료.
    stop, reason = assess_early_stop(
        _fit(grade="보통"),
        _agg(click_intent_rate=0.7, purchase_intent=4.0, rejection_rate=0.1, effective_n=30),
    )
    assert stop is True
    assert reason


# ── 미종료(False) 케이스 — 오조기종료 방지 ──


def test_no_stop_when_low_confidence():
    # 높음 등급 + 충분표본이라도 low_confidence면 종료 금지.
    stop, reason = assess_early_stop(_fit(grade="높음", low_confidence=True), _agg(effective_n=30))
    assert stop is False
    assert reason == ""


def test_no_stop_when_variance_warning():
    stop, reason = assess_early_stop(
        _fit(grade="높음"), _agg(variance_warning=True, effective_n=30)
    )
    assert stop is False
    assert reason == ""


def test_no_stop_when_grade_not_high_and_kpi_below():
    stop, _ = assess_early_stop(_fit(grade="보통"), _agg(effective_n=30))
    assert stop is False


def test_no_stop_when_signals_missing():
    assert assess_early_stop(None, None) == (False, "")
    assert assess_early_stop(_fit(), None) == (False, "")
    assert assess_early_stop(None, _agg()) == (False, "")


# ── 경계값 ──


def test_boundary_effective_n_15_stops():
    # effective_n 임계 15 — 정확히 15면 종료(>=).
    stop, _ = assess_early_stop(_fit(grade="높음"), _agg(effective_n=15))
    assert stop is True


def test_boundary_effective_n_14_no_stop():
    # 14면 '높음' 규칙 미충족. KPI 임계도 미달이면 미종료.
    stop, _ = assess_early_stop(_fit(grade="높음"), _agg(effective_n=14))
    assert stop is False


def test_boundary_kpi_exactly_on_threshold_no_stop():
    # 임계는 초과(>)·미만(<) — 정확히 경계값이면 미충족.
    stop, _ = assess_early_stop(
        _fit(grade="낮음"),
        _agg(click_intent_rate=0.6, purchase_intent=3.5, rejection_rate=0.2, effective_n=30),
    )
    assert stop is False


# ── result_callback 통합 ──


def test_callback_early_stops_on_strong_signals():
    sid = "s-cb-earlystop"
    reset_loop_state(sid)
    _answer, meta = result_callback.handle(
        sid, objective_fit=_fit(grade="높음"), aggregate=_agg(effective_n=30)
    )
    assert meta.get("loop_done") is True
    assert meta.get("early_stop_reason")
    assert "approval" not in meta
    assert get_loop_state(sid).phase == "finished"
    assert get_loop_state(sid).early_stop_reason
    reset_loop_state(sid)


def test_callback_proposes_rerun_when_signals_weak():
    sid = "s-cb-weak"
    reset_loop_state(sid)
    _answer, meta = result_callback.handle(sid, objective_fit=_fit(grade="보통"), aggregate=_agg())
    assert meta.get("approval", {}).get("action") == "rerun_simulation"
    assert "early_stop_reason" not in meta
    assert get_loop_state(sid).phase == "gen_done"
    reset_loop_state(sid)
