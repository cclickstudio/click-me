"""🤝 contracts — ExecutionMode, ActionTier, CampaignState, AnomalyType, ProposalStatus."""

from enum import IntEnum, StrEnum


class ActionTier(IntEnum):
    """0~1 자율 통과 / 2 비활성(7/8 스코프 제외) / 3 사용자 라우팅."""

    TIER0 = 0
    TIER1 = 1
    TIER2 = 2
    TIER3 = 3


class AnomalyType(StrEnum):
    """게재 고장 5종(Mock 정답 라벨과 1:1) + 결정론 3종."""

    REVIEW_REJECTED = "review_rejected"
    REVIEW_DELAY = "review_delay"
    BID_LOSS = "bid_loss"
    AUDIENCE_TOO_NARROW = "audience_too_narrow"
    QUALITY_DEGRADED = "quality_degraded"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SCHEDULE_GAP = "schedule_gap"
    LEARNING_PHASE = "learning_phase"


class ExecutionMode(StrEnum):
    """값은 core/config.py, 강제는 executor 분기."""

    DRY_RUN = "dry_run"
    MOCK = "mock"
    LIVE = "live"


class ProposalStatus(StrEnum):
    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    STALE = "stale"


class DiagnosisSource(StrEnum):
    """결정론 경로 / agent 경로 구분."""

    DETERMINISTIC = "deterministic"
    AGENT = "agent"


class DiagnosisStatus(StrEnum):
    """INCONCLUSIVE만 agent로 라우팅된다."""

    CONFIRMED = "confirmed"
    INCONCLUSIVE = "inconclusive"
