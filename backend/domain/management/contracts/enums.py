"""🤝 contracts — 공용 Enum (A/B 유일한 접점).

[draft v1 — 🅱 작성 초안] contracts는 공동 소유 — 머지 전 🅰 리뷰 필수.
근거: docs/management/structure-and-roles.md §9.2 D1~D8,
docs/management/clickme_management_합의문서_v2.1안_2.md §3.1.
"""

from enum import IntEnum, StrEnum


class ExecutionMode(StrEnum):
    """실행 모드 격리 — 값은 설정, 강제는 executor 분기. v1에서 LIVE 비활성 (§7 Must)."""

    MOCK = "mock"
    DRY_RUN = "dry_run"
    SANDBOX_CONTRACT = "sandbox_contract"
    LIVE = "live"


class ActionTier(IntEnum):
    """D3 — 원칙: "줄이는 건 자율, 늘리는 건 승인"."""

    TIER_0 = 0  # 지표 조회·리포트 (자율)
    TIER_1 = 1  # 악화 광고 끄기 — 지출 ↓ (자율 + 즉시 알림)
    TIER_2 = 2  # 예산 재배분 — 총액 불변 (v1 자동 실행 비활성)
    TIER_3 = 3  # 예산 증액·신규 집행·시안 교체 (항상 건별 사용자 승인)


class CampaignState(StrEnum):
    """D2 — ACTIVE_PENDING_REVIEW 포함(권고안): 게재 중 변경분 비동기 심사."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    ACTIVE = "active"
    ACTIVE_PENDING_REVIEW = "active_pending_review"
    PAUSED = "paused"
    ENDED = "ended"


class AnomalyType(StrEnum):
    """D1 — Mock 고장모드 = AnomalyType = 진단 출력 = eval 정답 (넷이 같은 enum)."""

    REVIEW_REJECTED = "review_rejected"  # 심사 거절 (고장 5종)
    REVIEW_DELAY = "review_delay"  # 심사 지연 (고장 5종)
    BID_LOSS = "bid_loss"  # 입찰 패배 (고장 5종 — 데모 중심축)
    AUDIENCE_TOO_NARROW = "audience_too_narrow"  # 타겟 협소 (고장 5종)
    QUALITY_DEGRADED = "quality_degraded"  # 품질 저하 (고장 5종)
    BUDGET_EXHAUSTED = "budget_exhausted"  # 예산 소진 (결정론 진단 영역)
    SCHEDULE_GAP = "schedule_gap"  # 일정 문제 (결정론)
    LEARNING_PHASE = "learning_phase"  # 학습 기간 (결정론)
    INCONCLUSIVE = "inconclusive"  # 규칙엔진 판단 불가 → agent 라우팅


class ProposalStatus(StrEnum):
    """합의문서 v2.1 §3.1 [안]."""

    DRAFT = "draft"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    STALE = "stale"


class ResultStatus(StrEnum):
    """D7 — SUBMITTED_PENDING_REVIEW 없으면 Meta 비동기 심사에 일주일 안에 깨진다."""

    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    SUBMITTED_PENDING_REVIEW = "pending_review"


class FailureReason(StrEnum):
    """D7 — 자유 문자열 금지: eval 기계 채점용 enum."""

    # D7 합의 초안 4종
    TIMEOUT = "timeout"
    BUDGET_CAP_EXCEEDED = "budget_cap_exceeded"
    PLATFORM_ERROR = "platform_error"
    INVALID_TIER = "invalid_tier"
    # 🅱 추가분 — executor 4~7단계 거부 사유 (게이트 #1~#4 기계 채점)
    PROPOSAL_EXPIRED = "proposal_expired"
    APPROVAL_EXPIRED = "approval_expired"
    PROPOSAL_HASH_MISMATCH = "proposal_hash_mismatch"
    TENANT_MISMATCH = "tenant_mismatch"
    UNAPPROVED_ACTION = "unapproved_action"
    STALE_PROPOSAL = "stale_proposal"  # expected_state_version·정책버전 불일치 → 새 제안
    UNSUPPORTED_ACTION = "unsupported_action"
    EXECUTION_MODE_DISABLED = "execution_mode_disabled"  # LIVE 등 비활성 모드
    RATE_LIMITED = "rate_limited"
    PARTIAL_FAILURE = "partial_failure"  # 다중 타겟 일부 성공 후 실패 — 정지(P5)


class FaultMode(StrEnum):
    """D8 — 고장 주입. 🅱 테스트가 contracts 경유로 Mock 고장을 켠다."""

    WRITE_TIMEOUT = "write_timeout"
    REVIEW_STUCK = "review_stuck"
    RATE_LIMITED = "rate_limited"
    # 🅱 추가분 — executor 테스트 시나리오 (게이트 #2, #7)
    PARTIAL_FAILURE = "partial_failure"
    STATE_VERSION_DRIFT = "state_version_drift"
