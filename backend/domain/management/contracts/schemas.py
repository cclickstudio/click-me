"""🤝 contracts — Pydantic v2 DTO (A/B 유일한 접점).

[통합본 v1] 🅰 초안 + 🅱 초안 머지. 스튜어드 기준으로 채택:
진단측(DiagnosisResult·MetricsSnapshot)=🅰안 / 액션측(ActionProposal·ActionResult·
FaultConfig)=🅱안 / 경계측(ApprovedAction)=공동 — PK는 ``approval_id`` (D6+ERD).

공통 규칙 (합의문서 v2.1 §2 + §9.0 그라운드 룰): 모든 모델
``ConfigDict(extra="forbid", frozen=True)`` · 타임스탬프 UTC aware datetime(naive 금지) ·
통화 KRW 정수(float 금지, ``_krw`` 접미) · 모든 계약에 ``schema_version`` 포함 ·
골든 샘플은 ``evals/fixtures/contracts/``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from domain.management.contracts.enums import (
    ActionTier,
    AnomalyType,
    CampaignState,
    DiagnosisSource,
    DiagnosisStatus,
    ExecutionMode,
    FailureReason,
    FaultMode,
    ProposalStatus,
    RelevanceRank,
    ResultStatus,
)

SCHEMA_VERSION: Final[str] = "1.0"

#: Tier 0~1 자율 통과 시 approver_id 값 (D6)
AUTO_APPROVER: Final[str] = "AUTO"


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("naive datetime 금지 — UTC aware datetime만 허용 (합의문서 §2)")
    return value


UtcDatetime = Annotated[datetime, AfterValidator(_require_utc)]


class Contract(BaseModel):
    """모든 계약의 공통 베이스 — extra='forbid'로 합의 안 된 필드 차단 (§9.0)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SCHEMA_VERSION


class CampaignConfig(Contract):
    """캠페인 설정 — v1 초안 (세부 필드 개정 시한: §5)."""

    campaign_id: str
    tenant_id: str
    ad_account_id: str
    name: str | None = None  # 사용자 지정 캠페인 이름 (없으면 writer가 clickme-{id} 폴백)
    objective: Literal["traffic", "leads"] = "traffic"  # 트래픽(클릭) / 리드(잠재고객)
    daily_budget_krw: int = Field(ge=0)
    start_at: UtcDatetime
    end_at: UtcDatetime
    creative_ad_id: str | None = None  # core Ad 느슨 참조 (FK 없음)
    image_hash: str | None = None  # Meta /adimages 업로드 해시 — 광고 소재 이미지(없으면 텍스트만)
    # Meta 타겟·정책 — 광고세트 targeting + 캠페인 special_ad_categories로 매핑된다.
    special_ad_categories: tuple[str, ...] = ()  # () | ("HOUSING",) | ("EMPLOYMENT",) 등
    countries: tuple[str, ...] = ("KR",)  # geo_locations.countries (ISO2)
    age_min: int = Field(default=18, ge=18, le=65)  # Meta 최소 연령 18
    age_max: int = Field(default=65, ge=18, le=65)
    genders: tuple[int, ...] = ()  # () = 전체, (1,) = 남성, (2,) = 여성 (Meta 코드)
    target_audience: dict[str, Any] = Field(default_factory=dict)


class CampaignInfo(Contract):
    """캠페인 목록 항목 — 대시보드용 (AdPlatformReader.list_campaigns 산출).

    이름·상태·일예산만 담는 경량 DTO. 성과 지표는 get_metrics로 별도 조회.
    """

    campaign_id: str
    name: str
    state: CampaignState
    daily_budget_krw: int = Field(ge=0)
    ended_at: str | None = None  # 게재 종료일(ISO) — 캠페인 stop_time 또는 광고세트 종료일


class MetricsSnapshot(Contract):
    """D9 — 시간별(hourly) 지표. reach/frequency는 누적값 (시간행 단순 합산 금지).

    필드 구성은 🅰 기대 노출 모델(일중 곡선) 요구 기준 — 스튜어드 🅰.
    """

    campaign_id: str
    as_of: UtcDatetime
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    inline_link_clicks: int = Field(ge=0)
    spend_krw: int = Field(ge=0)
    cum_impressions: int = Field(ge=0)
    cum_reach: int = Field(ge=0)
    frequency: float = Field(ge=0.0)
    ctr: float = Field(ge=0.0)
    cpm_krw: int = Field(ge=0)
    cpc_krw: int = Field(ge=0)
    conversions: int | None = Field(default=None, ge=0)
    purchase_value_krw: int | None = Field(default=None, ge=0)
    cvr: float | None = Field(default=None, ge=0.0)
    roas: float | None = Field(default=None, ge=0.0)


class RealOutcome(Contract):
    """집행 후 실측 성과 — 캘리브레이션(시뮬 예측 vs 실측) 소비용 계약.

    크리에이티브 기준 귀속(creative_id)으로 "어떤 안을 집행했더니 실제로 이랬다"를 노출한다.
    전환(conversions·cvr)은 픽셀/CAPI 미설정이면 None — 합성 금지(정직).
    """

    creative_id: str | None = None  # 집행된 크리에이티브 (미연결이면 None)
    campaign_id: str
    impressions: int = Field(ge=0)
    reach: int = Field(ge=0)
    spend_krw: int = Field(ge=0)
    ctr: float = Field(ge=0.0)
    cpc_krw: int = Field(ge=0)
    cpm_krw: int = Field(ge=0)
    conversions: int | None = None
    cvr: float | None = None
    roas: float | None = None  # 매출÷지출 — 전환 가치 추적 전이면 None(측정 불가)
    as_of: UtcDatetime


class PlatformMetrics(Contract):
    """게재 플랫폼별(publisher_platform) 지표 분해 — facebook/instagram/audience_network 등."""

    platform: str
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    spend_krw: int = Field(ge=0)
    reach: int = Field(ge=0)


class DemographicMetrics(Contract):
    """연령×성별(age,gender breakdown) 지표 분해 — Meta age 버킷 × male/female/unknown."""

    age: str
    gender: str
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    spend_krw: int = Field(ge=0)
    reach: int = Field(ge=0)


class CreativePreview(Contract):
    """광고 크리에이티브 미리보기 — 캠페인 대표 시안(광고명·이미지·문구).

    image_url은 원본 해상도(카드 표시용), thumbnail_url은 폴백용 소형 썸네일.
    """

    ad_id: str
    ad_name: str
    image_url: str | None = None  # 원본 해상도 (카드 메인 이미지)
    thumbnail_url: str | None = None  # 소형 썸네일 (image_url 없을 때 폴백)
    headline: str | None = None  # 광고 제목(creative.title)
    primary_text: str | None = None  # 기본 문구(creative.body)


class AccountFunding(Contract):
    """광고계정 자금·게재 가능 여부 — 선불 잔액 소진·계정 비활성 감지(게재 중단 원인)."""

    account_status: int
    available_balance_krw: int | None = None  # 선불 가용 잔액 (모르면 None)
    spend_cap_krw: int | None = None  # 계정 지출 한도(선불이면 충전액과 일치, 부가세 별도)
    amount_spent_krw: int | None = None  # 계정 누적 지출(광고 집행분, 부가세 별도)
    delivery_blocked: bool = False
    block_reason: str | None = None  # "선불 잔액 부족" · "계정 비활성" 등


class DeliveryEstimate(Contract):
    """Meta delivery_estimate 대응 — 미래 예측치(forecast), 성과 아님."""

    campaign_id: str
    estimate_ready: bool
    estimate_mau_lower: int = Field(ge=0)
    estimate_mau_upper: int = Field(ge=0)
    daily_outcomes_curve: tuple[dict[str, Any], ...] = ()
    as_of: UtcDatetime


class RelevanceDiagnostics(Contract):
    """Ad Relevance Diagnostics — 메타 본인 채점표 (meta-data-sources §2②).

    광고(ad) 단위 경쟁 대비 백분위. QUALITY_DEGRADED 1차 신호 + conversion_rate_ranking은
    성과 미달(PERFORMANCE_BELOW_TARGET) 진단 신호. 미설정/저노출이면 UNKNOWN(합성 금지).
    """

    campaign_id: str
    quality_ranking: RelevanceRank = RelevanceRank.UNKNOWN
    engagement_rate_ranking: RelevanceRank = RelevanceRank.UNKNOWN
    conversion_rate_ranking: RelevanceRank = RelevanceRank.UNKNOWN
    as_of: UtcDatetime


class DeliveryStatusDetail(Contract):
    """상태·심사·학습 상세 (meta-data-sources §3.1) — Insights 아닌 Ad/AdSet 객체에서.

    REVIEW_*/LEARNING_PHASE 감지용. get_state(CampaignState)와 별개의 상세 신호.
    """

    campaign_id: str
    effective_status: str  # ACTIVE / PAUSED / DISAPPROVED / PENDING_REVIEW ...
    issues_info: tuple[str, ...] = ()  # 심사 거절/제한 사유
    learning_stage: str | None = None  # LEARNING / SUCCESS / FAIL (adset)
    as_of: UtcDatetime


class DiagnosisResult(Contract):
    """🅰 → 🅱 단일 진단 계약 (v2.1 §2.1) — 스튜어드: 🅰.

    ``evidence_metrics`` 는 정보 방화벽 — agent가 이 밖의 정보로 추론하는 것 금지.
    """

    diagnosis_id: str
    tenant_id: str  # organization_id 정렬
    campaign_id: str
    anomaly_type: AnomalyType
    source: DiagnosisSource
    hypothesis: str = ""  # 원인 가설 (agent 산출 시)
    confidence: float = Field(ge=0.0, le=1.0)  # 결정론 경로는 1.0
    evidence_metrics: dict[str, Any] = Field(default_factory=dict)
    metrics_as_of: UtcDatetime
    status: DiagnosisStatus  # INCONCLUSIVE만 agent로 라우팅


class ActionProposal(Contract):
    """🅱 단독 생산 → 승인 플레인 — 필드 18종 [확정: 변경 없음] (§4). 스튜어드: 🅱.

    ``action_type`` 어휘는 contracts/policy.py의 TIER_POLICY 키가 정본 (P1).
    """

    proposal_id: str
    tenant_id: str
    ad_account_id: str
    target_object_ids: tuple[str, ...] = Field(min_length=1)  # ads 느슨 참조
    action_type: str  # 예: "PAUSE_CAMPAIGN" / "INCREASE_BUDGET" / "REPLACE_CREATIVE"
    action_tier: ActionTier  # 🅱의 제안 라벨 — 판정 정본은 approval.py(🅰)
    evidence_metrics: dict[str, Any] = Field(default_factory=dict)
    metrics_as_of: UtcDatetime
    hypothesis: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    expected_state_version: str  # executor 5)단계 낙관적 락 비교용
    budget_before_krw: int = Field(ge=0)
    budget_after_krw: int = Field(ge=0)
    max_total_spend_krw: int = Field(ge=0)  # P4 산식: budget_after × 집행 예상일수
    expires_at: UtcDatetime  # P3 TTL — 데모 10분 (policy.PROPOSAL_TTL_MINUTES)
    proposal_hash: str = ""  # finalize_proposal()로 채움 — 변조 감지
    approval_policy_version: str
    status: ProposalStatus = ProposalStatus.PENDING


class ApprovedAction(Contract):
    """승인 플레인(🅰) → executor(🅱) — 경계 계약, 확정 후 frozen (D6 + v2.1 §2.3).

    PK 이름은 ``approval_id`` (D6 코드블록 + ERD approvals.approval_id 채택).
    발급자는 approval.py(🅰)뿐. executor(🅱)는 검증만 한다.
    승인 = 실행 자격(executor 4단계 재검증 통과 필요)이며 실행 보장이 아니다.
    """

    approval_id: str  # 승인 자체의 ID — 중복승인 멱등 키의 축
    proposal_id: str
    proposal_hash: str  # 발급 시점 스냅샷 — executor 재검증용 (제안 변조 감지)
    tenant_id: str
    approver_id: str  # 사용자 ID 또는 AUTO_APPROVER (Tier 0~1 자율 통과)
    action_tier: ActionTier  # approval.py 판정 Tier (정본)
    approved_at: UtcDatetime
    expires_at: UtcDatetime  # 승인 자체의 만료 — 제안 TTL보다 짧게 (P3)
    approval_policy_version: str  # 승인~실행 갭 사이 정책 변경 감지
    expected_state_version: str  # 제안에서 승계
    execution_mode: ExecutionMode


class ActionResult(Contract):
    """🅱 → 감사·표시 (v2.1 §2.4). ``approval_id`` = ApprovedAction PK 참조."""

    result_id: str
    approval_id: str
    status: ResultStatus
    failure_reason: FailureReason | None = None  # 자유 문자열 금지 — 기계 채점용
    platform_response_snapshot: dict[str, Any] | None = None
    executed_at: UtcDatetime | None = None
    idempotency_key: str


class FaultConfig(Contract):
    """고장 주입 — 🅱가 contracts 경유로만 Mock 고장을 켠다 (별도 파일 없음, §1)."""

    mode: FaultMode
    probability: float = Field(default=1.0, ge=0.0, le=1.0)


# ── proposal_hash 유틸 — 생산(🅱)·승인(🅰)·실행(🅱)이 같은 산식을 공유한다 ──
# [통합 결정] 전체 필드 해시(🅱안) 채택 — 5개 필드 부분 해시(🅰안)보다 변조 탐지
# 범위가 넓다 (evidence·만료·예산 변조까지 잡는다). 산식은 양쪽이 반드시 공유.
# 제외 3종은 라이프사이클상 합법적으로 변하는 필드: status(상태 전이),
# action_tier(approval.py의 재라벨 판정 — P1 "판정 Tier로 재라벨 후 진행").

_HASH_EXCLUDED: Final[frozenset[str]] = frozenset({"proposal_hash", "status", "action_tier"})


def compute_proposal_hash(proposal: ActionProposal) -> str:
    """status·proposal_hash를 제외한 정규화 JSON의 sha256 — 제안 변조 감지."""
    payload = proposal.model_dump(mode="json", exclude=set(_HASH_EXCLUDED))
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def finalize_proposal(proposal: ActionProposal) -> ActionProposal:
    """proposal_hash를 계산해 채운 사본 반환 — 생산 직후 1회 호출."""
    return proposal.model_copy(update={"proposal_hash": compute_proposal_hash(proposal)})


def verify_proposal_hash(proposal: ActionProposal) -> bool:
    return proposal.proposal_hash == compute_proposal_hash(proposal)
