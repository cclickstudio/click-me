# 채팅 카드 봉투 계약 — kind(닫힌 슬롯) + payload.type/version(열린 확장점). 순수 계약 모듈.
from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class CardKind(StrEnum):
    EVIDENCE = "evidence"
    RESULT = "result"
    REVIEW = "review"
    ACTIONBAR = "actionbar"


class CardStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class TurnOrigin(StrEnum):
    USER = "user"
    PROACTIVE = "proactive"


class CardPayload(BaseModel):
    type: str  # 슬롯 안의 변종 (rag_citations / action_proposal / policy_check / actions ...)
    version: int = 1
    data: dict[str, Any] = Field(default_factory=dict)


class Card(BaseModel):
    kind: CardKind
    status: CardStatus = CardStatus.OK
    payload: CardPayload


class TurnEnvelope(BaseModel):
    turn_id: str
    origin: TurnOrigin = TurnOrigin.USER  # 기본 user — 필드 없으면 user로 간주
    conclusion: str  # 항상, 서술만(불변식 ③ — Composer 서술 가드 통과)
    cards: list[Card] = Field(default_factory=list)
    # 능동 제안 전용(origin=proactive일 때만) — 후속 plan에서 채움
    trigger: dict[str, Any] | None = None
    read_state: Literal["unread", "read"] | None = None
