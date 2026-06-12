"""★① contracts — FaultMode / FaultConfig. 🅱가 executor 테스트 시 import."""

from enum import StrEnum

from pydantic import BaseModel


class FaultMode(StrEnum):
    # 🅱 실행(쓰기) 고장 — executor 테스트 시나리오
    WRITE_TIMEOUT = "write_timeout"
    REVIEW_STUCK = "review_stuck"
    RATE_LIMITED = "rate_limited"
    # 🅰 게재 고장 5종 — AnomalyType eval 정답 라벨과 1:1 (meta-data-sources.md §4.5)
    BID_LOSS = "bid_loss"
    AUDIENCE_TOO_NARROW = "audience_too_narrow"
    QUALITY_DEGRADED = "quality_degraded"
    REVIEW_REJECTED = "review_rejected"
    REVIEW_DELAY = "review_delay"


class FaultConfig(BaseModel):
    mode: FaultMode
    probability: float = 1.0
