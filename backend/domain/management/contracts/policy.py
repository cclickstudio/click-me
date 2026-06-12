"""🤝 정책 값 단일 소스 — 판정은 approval.py, 집행은 executor (R&R §8).

같은 정책을 두 곳에 하드코딩하지 않는다. Mock 생성과 detection 기준선이
같은 앵커·곡선을 공유해야 정상 케이스가 오탐되지 않는다 (게이트 #5).
"""

from domain.management.contracts.enums import ActionTier

APPROVAL_POLICY_VERSION = "v1"

# ── P1. Tier 매핑 정책표 (정본 — 제안의 action_tier는 라벨일 뿐) ──
TIER_POLICY: dict[str, ActionTier] = {
    "GET_INSIGHTS": ActionTier.TIER_0,
    "PREVIEW_AD": ActionTier.TIER_0,
    "PAUSE_CAMPAIGN": ActionTier.TIER_1,
    "DECREASE_BUDGET": ActionTier.TIER_1,
    "REBALANCE_BUDGET": ActionTier.TIER_2,  # 비활성 (7/8 스코프 제외)
    "INCREASE_BUDGET": ActionTier.TIER_3,
    "REPLACE_CREATIVE": ActionTier.TIER_3,
}

AUTO_APPROVE_MAX_TIER = ActionTier.TIER_1

# ── P3. TTL (데모 모드) — 승인 TTL은 제안 TTL보다 짧다 (불변) ──
PROPOSAL_TTL_MINUTES = 10
APPROVAL_TTL_MINUTES = 5

# ── Mock 앵커 (meta-data-sources.md §4.4 — 한국 인스타 트래픽 기준) ──
CPM_ANCHOR_KRW = 8_000
CPM_NORMAL_RANGE_KRW = (6_000, 14_000)
BASE_CTR = 0.017
DAILY_BUDGET_KRW = 100_000
AUDIENCE_SIZE = 1_750_000  # delivery_estimate estimate_mau 기반 데모 모수

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
