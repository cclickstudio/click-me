"""🤝 정책 값 단일 소스 — 판정은 approval.py, 집행은 executor (R&R §8).

같은 정책을 두 곳에 하드코딩하지 않는다. Mock 생성과 detection 기준선이
같은 앵커·곡선을 공유해야 정상 케이스가 오탐되지 않는다 (게이트 #5).
"""

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
    "REBALANCE_BUDGET": ActionTier.TIER_2,  # 비활성 (7/8 스코프 제외)
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
