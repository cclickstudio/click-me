# 🅰 오가닉↔광고 비교 A-로컬 DTO·enum (아직 A↔B 공유 계약 아님 — 승격 시 contracts/로 이전)
"""비교 산출물 스키마. Contract 베이스(frozen·extra=forbid·schema_version) 재사용."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from domain.management.contracts.schemas import Contract, UtcDatetime


class PostType(StrEnum):
    ORGANIC = "organic"  # 일반 게시물
    PAID = "paid"  # 광고 집행 게시물


class LiftVerdict(StrEnum):
    PASS = "pass"  # 통과 — 유의미한 증분
    CAUTION = "caution"  # 주의 — 약한 증분
    FAIL = "fail"  # 미달 — 증분 부족


class PostInsights(Contract):
    """단일 게시물 지표 — 오가닉 또는 광고. reach/impressions는 누적 기준."""

    post_id: str
    post_type: PostType
    as_of: UtcDatetime
    reach: int = Field(ge=0)
    impressions: int = Field(ge=0)
    engagement: int = Field(ge=0)  # 좋아요+댓글+저장+공유(오가닉) / 상호작용(광고)
    clicks: int = Field(ge=0)  # 링크 클릭(광고), 오가닉은 0
    spend_krw: int = Field(ge=0)  # 오가닉 0


class LiftResult(Contract):
    """오가닉→광고 증분 효과 + 판정. 🅰 내부 분석 산출물."""

    post_id: str  # 비교 기준 = 오가닉 게시물 id
    organic: PostInsights
    paid: PostInsights
    reach_lift_abs: int  # 증분 도달 (광고 - 오가닉)
    reach_lift_ratio: float = Field(ge=0.0)  # 도달 배수
    impressions_lift_abs: int  # 증분 노출
    verdict: LiftVerdict
    computed_at: UtcDatetime
