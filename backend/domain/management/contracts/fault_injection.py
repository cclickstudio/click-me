"""★① contracts — FaultMode / FaultConfig. 🅱가 executor 테스트 시 import."""

from enum import StrEnum

from pydantic import BaseModel


class FaultMode(StrEnum):
    WRITE_TIMEOUT = "write_timeout"
    REVIEW_STUCK = "review_stuck"
    RATE_LIMITED = "rate_limited"


class FaultConfig(BaseModel):
    mode: FaultMode
    probability: float = 1.0
