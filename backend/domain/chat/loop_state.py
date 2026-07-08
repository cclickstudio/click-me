# 개선 루프 상태 — 시뮬↔제너 왕복(최대 3회) HITL 컨트롤러의 세션별 인메모리 상태
"""시뮬 결과가 약하면 개선 시안 생성을 제안(approval)하고, 수락 시 왕복을 1회 카운트한다.
서버 프로세스 메모리에만 보관(재시작 시 초기화). 오케스트레이터와 /approve 라우터가 공유.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if (
    TYPE_CHECKING
):  # 타입 힌트 전용 — 런타임에 시뮬 도메인을 import하지 않는다(경계 유지·duck typing).
    from domain.simulation.contracts.schemas import ObjectiveFit, SimulationAggregate

MAX_LOOP = 3  # 시뮬↔제너 왕복 최대 횟수

# 조기 종료 임계 — '높음' 등급을 인정할 최소 유효표본(Kish). 표본이 너무 작으면 조기종료 금지.
_EARLY_STOP_MIN_EFFECTIVE_N = 15.0
# KPI 임계 — 등급과 무관하게 이 세 조건을 모두 넘으면 목표 충족으로 본다.
_KPI_MIN_CLICK = 0.6
_KPI_MIN_PURCHASE = 3.5
_KPI_MAX_REJECTION = 0.2


@dataclass
class LoopState:
    loop_count: int = 0  # 최대 MAX_LOOP
    phase: str = "idle"  # idle | sim_done | gen_done | finished
    last_sim_id: str | None = None
    last_gen_id: str | None = None
    weak_reasons: list[str] = field(default_factory=list)
    early_stop_reason: str | None = None  # KPI 등급 기반 조기종료 사유(없으면 미조기종료)


def assess_early_stop(
    objective_fit: ObjectiveFit | None,
    aggregate: SimulationAggregate | None,
) -> tuple[bool, str]:
    """직전 시뮬 KPI 등급으로 개선 왕복을 조기 종료할지 판정 — (종료여부, 사유).

    loop_count 누적이 아니라 KPI 등급 기반이라 인메모리 초기화(서버 재시작) 영향을 안 받는다.
    오조기종료 방지가 최우선 — 신뢰 낮음/분산 경고면 무조건 계속(False)한다.
    """
    if objective_fit is None or aggregate is None:
        return (False, "")
    # ① 신뢰 부족 방어 — 유효표본 부족(low_confidence)·구매의도 분산 경고면 판정 보류.
    if objective_fit.low_confidence or aggregate.variance_warning:
        return (False, "")
    # ② 목표 적합도 '높음' + 충분표본 — 가장 강한 종료 신호.
    if objective_fit.grade == "높음" and aggregate.effective_n >= _EARLY_STOP_MIN_EFFECTIVE_N:
        return (
            True,
            f"목표 적합도 '높음'(점수 {objective_fit.score}) · "
            f"유효표본 {aggregate.effective_n:.0f}명으로 충분",
        )
    # ③ 4대 KPI 임계 동시 충족 — 등급과 무관하게 목표 달성으로 본다.
    if (
        aggregate.click_intent_rate > _KPI_MIN_CLICK
        and aggregate.purchase_intent > _KPI_MIN_PURCHASE
        and aggregate.rejection_rate < _KPI_MAX_REJECTION
    ):
        return (
            True,
            f"KPI 임계 충족(클릭의향 {aggregate.click_intent_rate:.0%} · "
            f"구매의도 {aggregate.purchase_intent:.1f} · 거부율 {aggregate.rejection_rate:.0%})",
        )
    return (False, "")


_store: dict[str, LoopState] = {}


def _key(session_id: str | None) -> str:
    return session_id or "__ephemeral__"


def get_loop_state(session_id: str | None) -> LoopState:
    key = _key(session_id)
    st = _store.get(key)
    if st is None:
        st = LoopState()
        _store[key] = st
    return st


def reset_loop_state(session_id: str | None) -> None:
    _store.pop(_key(session_id), None)
