# 시뮬레이터 도메인 enum taxonomy — 반응 구조화의 고정 어휘 (REPORT §2-3과 동기화)
from __future__ import annotations

from enum import StrEnum


class SimulationStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class PanelStatus(StrEnum):
    BUILDING = "BUILDING"
    READY = "READY"


class TargetMode(StrEnum):
    AUTO = "AUTO"
    MANUAL = "MANUAL"


class AisasStage(StrEnum):
    ATTENTION = "attention"
    INTEREST = "interest"
    SEARCH = "search"
    ACTION = "action"
    SHARE = "share"


class DropReasonTag(StrEnum):
    """이탈 사유 taxonomy — LLM이 직접 enum으로 출력 (자유 텍스트 금지)."""

    NO_REASON_TO_EXPLORE = "no_reason_to_explore"
    PRICE_CONCERN = "price_concern"
    LOW_RELEVANCE = "low_relevance"
    UNCLEAR_MESSAGE = "unclear_message"
    DISTRUST = "distrust"
    OTHER = "other"


class RejectionReasonTag(StrEnum):
    """거부 사유 taxonomy."""

    IRRELEVANT = "irrelevant"
    OFFENSIVE = "offensive"
    OVERPRICED = "overpriced"
    DISTRUST = "distrust"
    AD_FATIGUE = "ad_fatigue"
    OTHER = "other"


class EmotionTag(StrEnum):
    """감정 반응 taxonomy."""

    CURIOSITY = "curiosity"
    DELIGHT = "delight"
    TRUST = "trust"
    INDIFFERENCE = "indifference"
    ANNOYANCE = "annoyance"
    DISTRUST = "distrust"
    OTHER = "other"
