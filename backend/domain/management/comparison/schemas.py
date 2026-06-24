# 🅰 오가닉↔광고 비교 A-로컬 DTO·enum (아직 A↔B 공유 계약 아님 — 승격 시 contracts/로 이전)
"""비교 산출물 스키마. Contract 베이스(frozen·extra=forbid·schema_version) 재사용."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from domain.management.contracts.schemas import Contract, RealOutcome, UtcDatetime


class PostType(StrEnum):
    ORGANIC = "organic"  # 일반 게시물
    PAID = "paid"  # 광고 집행 게시물


class LiftVerdict(StrEnum):
    PASS = "pass"  # 통과 — 유의미한 증분
    CAUTION = "caution"  # 주의 — 약한 증분
    FAIL = "fail"  # 미달 — 증분 부족


class RecommendedAction(StrEnum):
    """🅰 분석 추천 신호 — 제안(ActionProposal·🅱) 생성 전 단계의 권고."""

    SCALE_UP = "scale_up"  # 광고가 증분 도달을 크게 만듦 → 증액 검토
    HOLD = "hold"  # 약한 증분 → 유지·관찰
    PAUSE = "pause"  # 증분 미미 → 중단·감액 검토


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


class ComparisonRecommendation(Contract):
    """🅰 추천 신호 — LiftResult → 권고 액션. 🅱가 읽어 ActionProposal로 감싸는 seam.

    제안 생성·Tier 판정은 🅱(executor·approval) 책임이며, suggested_action_type은
    공유 정책표(TIER_POLICY) 키의 힌트일 뿐 강제가 아니다(정보 방화벽).
    """

    post_id: str  # 비교 기준 = 오가닉 게시물 id
    verdict: LiftVerdict
    recommended_action: RecommendedAction
    suggested_action_type: str = ""  # 🅱 TIER_POLICY 키 힌트 (없으면 빈 문자열)
    reach_lift_ratio: float = Field(ge=0.0)
    rationale: str
    computed_at: UtcDatetime


class ComparisonReport(Contract):
    """🅰 비교 1회 산출물 묶음 — 상세 리프트 + 권고. 표시·전달 계층 입력."""

    lift: LiftResult
    recommendation: ComparisonRecommendation


# ── 집행 전(시뮬 예측) vs 후(실측) 비교 — 시뮬과 느슨 결합용 슬롯 ──


class PredictionSnapshot(Contract):
    """집행 전 시뮬 예측 — 실 시뮬 KPI와 동일 필드(슬롯). Mock(데모) 또는 실 시뮬로 채움.

    예측은 상대 지표(클릭의향률 0~1·구매의도/신뢰도 1~5)다.
    실측(RealOutcome, 절대)과 스케일이 달라 환산하지 않고 나란히 둔다(CLAUDE.md).
    """

    ad_id: str
    click_intent_rate: float = Field(ge=0.0)  # 0~1
    purchase_intent: float = Field(ge=0.0)  # 1~5
    trust_avg: float = Field(ge=0.0)  # 1~5
    rejection_rate: float = Field(ge=0.0)  # 0~1
    as_of: UtcDatetime
    source: str = "mock"  # mock | sim — 슬롯이 무엇으로 채워졌는지


class BeforeAfterVerdict(StrEnum):
    ALIGNED = "aligned"  # 예측과 실측 방향 일치
    OVERPERFORMED = "overperformed"  # 예측보다 실측 좋음
    UNDERPERFORMED = "underperformed"  # 예측보다 실측 약함
    UNKNOWN = "unknown"  # 예측 없음(시뮬 미연결) 또는 판단 보류


class BeforeAfter(Contract):
    """캠페인 1건의 전(예측)·후(실측) 묶음 + 정성 방향성 판정.

    prediction이 None이면 시뮬 미연결(슬롯 비어있음) — 화면은 '시뮬 연결 대기'로.
    """

    campaign_id: str
    name: str
    prediction: PredictionSnapshot | None
    actual: RealOutcome
    verdict: BeforeAfterVerdict
    rationale: str
    interpretation: str = ""  # 보조 KPI(구매의도·신뢰도·거부율) 기반 결정론 해석 — 없으면 ""
