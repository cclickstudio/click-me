"""🤝 정책 값 단일 소스 — 판정은 approval.py, 집행은 executor (R&R §8).

같은 정책을 두 곳에 하드코딩하지 않는다. Mock 생성과 detection 기준선이
같은 앵커·곡선을 공유해야 정상 케이스가 오탐되지 않는다 (게이트 #5).
"""

from typing import Final

from domain.management.contracts.enums import ActionTier

APPROVAL_POLICY_VERSION = "v1"

# ── 재생성 decide 확신도 게이트 임계 (B) — 이 미만이면 돈 늘리는 처방을 관망으로 강등 ──
DECIDE_CONFIDENCE_MIN = 0.5

# ── P1. Tier 매핑 정책표 (정본 — 제안의 action_tier는 라벨일 뿐) ──
TIER_POLICY: dict[str, ActionTier] = {
    "GET_INSIGHTS": ActionTier.TIER_0,
    "PREVIEW_AD": ActionTier.TIER_0,
    "PAUSE_CAMPAIGN": ActionTier.TIER_1,
    "DECREASE_BUDGET": ActionTier.TIER_1,
    "REBALANCE_BUDGET": ActionTier.TIER_2,  # 총액 불변 이전 — 건별 사용자 승인(자율 실행 비활성)
    "INCREASE_BUDGET": ActionTier.TIER_3,
    "REPLACE_CREATIVE": ActionTier.TIER_3,
    "CREATE_CAMPAIGN": ActionTier.TIER_3,  # 신규 집행 — 항상 건별 사용자 승인 (PR2)
    "ACTIVATE_CAMPAIGN": ActionTier.TIER_3,  # 게재 시작(실과금) — 항상 건별 사용자 승인
    # 에스컬레이션 사다리 신규 액션 — 라이브 캠페인 개입(늘림) → 건별 승인.
    # CHANGE_BID_STRATEGY는 개념상 Tier 2 후보지만 Tier 2는 v1 자동 실행 비활성이라 Tier 3로 둔다.
    "EXPAND_AUDIENCE": ActionTier.TIER_3,
    "CHANGE_BID_STRATEGY": ActionTier.TIER_3,
}

AUTO_APPROVE_MAX_TIER = ActionTier.TIER_1

# ── 워커 A계열 룰 임계 — 지갑 소진·월 목표 가드레일 (홈 브리핑과 동일 기준) ──
WALLET_ALERT_PCT = 95  # 충전 한도 사용률 — 충전 필요
WALLET_WARN_PCT = 80  # 충전 한도 사용률 — 주의
DEFAULT_MONTHLY_TARGET_KRW = 3_000_000  # 월 목표 기본 — 중소기업 벤치마크(일 10만 페이스)

# ── 예산 리밸런싱 제안 임계 (insights.rebalance_proposal 단일 소스) ──
REBALANCE_STEP_PCT = 0.2  # 이동/조정 폭 — 저효율 일예산의 20%
REBALANCE_CPC_GAP = 1.2  # 2개+ 이전 게이트 — 저효율 CPC가 고효율의 1.2배 초과일 때만
REBALANCE_HIGH_UTIL = 0.9  # 1개 조정 — 7일 일예산 소진율 90%+면 예산 한도에 걸림 → 증액
REBALANCE_LOW_UTIL = 0.5  # 1개 조정 — 소진율 50% 이하면 예산이 게재보다 커 과다 → 감액
REBALANCE_MIN_MOVE_KRW = 1_000  # 이동/조정 최소 금액 — 이보다 작으면 제안 안 함

# ── P3. TTL (데모 모드) — 승인 TTL은 제안 TTL보다 짧다 (불변) ──
PROPOSAL_TTL_MINUTES = 10
APPROVAL_TTL_MINUTES = 5

# ── Mock 앵커 (meta-data-sources.md §4.4 — 한국 인스타 트래픽 실측 기준) ──
# CPM: 한국 실측 lebesgue $5.80(₩7,800) ~ AdAmigo $10.20(₩13,770), 2026 → 중앙값 ₩10,800.
CPM_ANCHOR_KRW = 10_800
CPM_NORMAL_RANGE_KRW = (7_800, 13_800)  # 한국 실측 하한(lebesgue)~상한(AdAmigo)
BASE_CTR = 0.017  # AdAmigo 2026 트래픽 목표 CTR 1.71%
DAILY_BUDGET_KRW = 100_000
AUDIENCE_SIZE = 1_750_000  # delivery_estimate estimate_mau 기반 데모 모수
FATIGUE_FREQUENCY = 3.0  # 빈도 3+ = 도달 피로(소재 교체 신호) — meta-data-sources.md §4.6

# ── 일중 곡선 (이중 봉우리: 점심 12~13시 / 저녁 20~23시) — 합 1로 정규화 ──
_PACING_RAW = [
    0.06,
    0.04,
    0.03,
    0.03,
    0.04,
    0.06,
    0.10,
    0.16,
    0.24,
    0.30,
    0.36,
    0.46,
    0.62,
    0.58,
    0.44,
    0.40,
    0.42,
    0.48,
    0.58,
    0.72,
    0.88,
    0.95,
    0.90,
    0.70,
]
HOURLY_PACING: list[float] = [w / sum(_PACING_RAW) for w in _PACING_RAW]

# ── 집행 권장 게이트 (스펙 2026-07-07 §4) — 시뮬 결과의 집행 가능 판정 단일 정본 ──
# 잠정 기본값(시뮬팀 확인 대상): 클릭 의향률 ≥1%(포함) · 거부율 <20%(미만).
# 실측 calibration 해금 전까지 settings(management_exec_gate_*)로만 조정한다.

EXEC_GATE_DEFAULT_MIN_CIR: Final[float] = 0.01
EXEC_GATE_DEFAULT_MAX_REJ: Final[float] = 0.2
# ⚠️ core/config.py management_exec_gate_min_cir/max_rej 기본값과 동일 유지.
# 경계 규칙상 리터럴 공유 불가 — 값 변경 시 양쪽 동시 수정.


def exec_gate_thresholds(settings) -> tuple[float, float]:
    """settings에서 임계값을 읽는다(덕타이핑 — contracts는 core 미의존)."""
    return (
        float(getattr(settings, "management_exec_gate_min_cir", EXEC_GATE_DEFAULT_MIN_CIR)),
        float(getattr(settings, "management_exec_gate_max_rej", EXEC_GATE_DEFAULT_MAX_REJ)),
    )


def is_executable_verdict(
    click_intent_rate: float, rejection_rate: float, *, min_cir: float, max_rej: float
) -> bool:
    """집행 권장 판정 — 클릭 의향률은 하한 포함(>=), 거부율은 상한 미만(<)."""
    return click_intent_rate >= min_cir and rejection_rate < max_rej
