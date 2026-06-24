# 🅱 재생성 에이전트 출력 — B→오케스트레이터 discriminated 타입 (A↔B 계약 아님)
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from domain.management.contracts.schemas import ActionProposal


class OutcomeKind(StrEnum):
    PROPOSED = "proposed"
    AWAITING_SELECTION = "awaiting_selection"
    OBSERVE = "observe"
    CREATIVE_UNAVAILABLE = "creative_unavailable"
    INPUT_INVALID = "input_invalid"
    FAILED = "failed"


class OutcomeReason(StrEnum):
    # OBSERVE
    ANOMALY_WATCH = "anomaly_watch"
    LOW_CONFIDENCE = "low_confidence"
    # CREATIVE_UNAVAILABLE 트리거 (스펙 §5e)
    GENERATOR_TIMEOUT = "generator_timeout"
    GENERATOR_UNAVAILABLE = "generator_unavailable"
    MISSING_CREATIVE_INPUT = "missing_creative_input"
    GENERATOR_EMPTY = "generator_empty"
    GUARD_WIPEOUT = "guard_wipeout"
    SCHEMA_INVALID = "schema_invalid"
    # fallback 복구 경로 (kind=PROPOSED)
    CREATIVE_FALLBACK_PAUSE = "creative_fallback_pause"
    CREATIVE_FALLBACK_EXPAND = "creative_fallback_expand"


class OutcomeError(StrEnum):
    UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class RemediationOutcome:
    kind: OutcomeKind
    proposal: ActionProposal | None = None  # PROPOSED일 때만
    candidates: list[dict[str, Any]] = field(default_factory=list)  # AWAITING_SELECTION
    selection_token: str | None = None  # AWAITING_SELECTION
    reason: OutcomeReason | None = None
    human_review_required: bool = False
    error_type: OutcomeError | None = None  # FAILED
