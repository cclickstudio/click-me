"""🤝 매니지먼트 얇은 엔드포인트 — 감지·진단·승인(HITL) 플로우 노출.

오케스트레이터('입')의 소유는 미정(R&R §6) — 본 라우터는 데모용 최소 구현이며
판정 로직은 전부 domain.management(approval.py 등)에 위임한다.
무상태(stateless): 프론트가 받은 제안을 그대로 돌려보내고, proposal_hash 재검증으로
변조를 감지한다 (승인 전 3단계 검증 시연).
"""

from datetime import UTC, datetime, timedelta
from random import Random
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.config import settings
from domain.management.adapters.mock import MockAdPlatform
from domain.management.agents.regeneration import RemediationContext
from domain.management.agents.regeneration_tools import build_regeneration_agent
from domain.management.approval import (
    approve,
    relabel_if_mismatch,
    requires_human,
    validate_proposal,
)
from domain.management.comparison.service.comparison_service import ComparisonService
from domain.management.contracts.enums import ActionTier, CampaignState
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.policy import (
    APPROVAL_POLICY_VERSION,
    DAILY_BUDGET_KRW,
    PROPOSAL_TTL_MINUTES,
)
from domain.management.contracts.schemas import (
    ActionProposal,
    ApprovedAction,
    CampaignConfig,
    DiagnosisResult,
    MetricsSnapshot,
    finalize_proposal,
)
from domain.management.demo import CAMPAIGN_ID, TENANT_ID, build_sample_proposal
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)
from domain.management.escalation import EscalationController
from domain.management.escalation_demo import DemoScenarioDetector
from domain.management.execution.executor import Executor
from domain.management.execution.tier import (
    ESCALATE_THRESHOLD,
    WARN_THRESHOLD,
    BudgetAuthority,
    TenantBudgetRegistry,
)
from domain.management.wiring import (
    build_audit_sink,
    build_comparison_service,
    build_escalation_store,
    build_idempotency_store,
    build_organic_reader,
    build_reader,
    build_writer,
)

router = APIRouter()

_DEMO_FAULTS = {"bid_loss", "review_rejected", "none"}

# use_mock=True(기본)면 인메모리, False면 DB(idempotency_keys·audit_events) — wiring 분기.
# 예산은 이번 범위 밖이라 인메모리 유지 (후속 B-1.2).
_AUDIT_LOG = build_audit_sink(settings)
_BUDGET = TenantBudgetRegistry(default_limit_krw=10_000_000)
_executor: Executor | None = None


async def _state_version(_ad_account_id: str) -> str:
    return "state_v1"  # 데모 고정 — 제안의 expected_state_version과 일치


def _get_executor() -> Executor:
    global _executor  # noqa: PLW0603
    if _executor is None:
        _executor = Executor(
            build_writer(settings),
            idempotency=build_idempotency_store(settings),
            audit=_AUDIT_LOG,
            budget_for=_BUDGET.for_tenant,
            state_version_provider=_state_version,
            current_policy_version=APPROVAL_POLICY_VERSION,
        )
    return _executor


@router.get("/run")
async def run_detection(fault: str = "bid_loss"):
    """감지 사이클 1회 실행: Mock 게재 → 기대 곡선 비교 → 결정론 진단 → 제안 검증."""
    if fault not in _DEMO_FAULTS:
        raise HTTPException(status_code=422, detail=f"fault는 {sorted(_DEMO_FAULTS)} 중 하나")

    fault_cfg = None if fault == "none" else FaultConfig(mode=FaultMode(fault))
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # 데이터 소스는 wiring 경유 — use_mock=True(기본)면 Mock+fault, False면 실 Meta reader.
    snapshots = await build_reader(settings).fetch_hourly_metrics(CAMPAIGN_ID, today, fault_cfg)
    expected = expected_hourly_impressions(DAILY_BUDGET_KRW)
    window = find_anomaly_window(expected, [s.impressions for s in snapshots])

    payload: dict = {
        "fault": fault,
        "expected": [round(e, 1) for e in expected],
        "snapshots": [s.model_dump(mode="json") for s in snapshots],
        "anomaly_hours": window,
        "diagnosis": None,
        "proposal": None,
        "relabeled": False,
        "requires_human": False,
        "validation_issues": [],
    }
    if not window:
        return payload

    dx = diagnose(TENANT_ID, CAMPAIGN_ID, snapshots, expected, window)
    proposal = build_sample_proposal(dx)
    proposal, relabeled = relabel_if_mismatch(proposal)

    payload.update(
        diagnosis=dx.model_dump(mode="json"),
        proposal=proposal.model_dump(mode="json"),
        relabeled=relabeled,
        requires_human=requires_human(proposal.action_tier),
        validation_issues=validate_proposal(proposal),
    )
    return payload


class ApprovalRequest(BaseModel):
    proposal: ActionProposal
    approved: bool
    approver_id: str = "user_demo"


@router.post("/approve")
async def approve_proposal(body: ApprovalRequest):
    """승인 플레인 — 3단계 검증(만료/해시/정책 버전) 후 ApprovedAction 발행."""
    issues = validate_proposal(body.proposal)
    if issues:
        raise HTTPException(status_code=409, detail={"issues": issues})

    if not body.approved:
        return {
            "status": "rejected",
            "detail": "거절됨 — 무승인 액션은 어떤 경로로도 Writer에 도달 불가 (불변 규칙 #2)",
        }

    action = approve(body.proposal, body.approver_id)
    return {"status": "approved", "approved_action": action.model_dump(mode="json")}


class RegenerateRequest(BaseModel):
    diagnosis: DiagnosisResult


@router.post("/regenerate")
async def regenerate(body: RegenerateRequest):
    """🅱 재생성 agent — 진단 수신 → 후보 생성·채점 → REPLACE_CREATIVE 제안 패키징."""
    agent = build_regeneration_agent()  # API 키 없으면 결정론 폴백
    context = RemediationContext(
        ad_account_id="act_demo_001",
        target_object_ids=(body.diagnosis.campaign_id,),
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        run_days=7,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    proposal = await agent.propose(body.diagnosis, context)
    if proposal is None:
        raise HTTPException(status_code=422, detail="생존 후보 없음 — 재생성 빈손")
    return {"proposal": proposal.model_dump(mode="json")}


class ExecuteRequest(BaseModel):
    approved_action: ApprovedAction
    proposal: ActionProposal


@router.post("/execute")
async def execute(body: ExecuteRequest):
    """🅱 executor — 승인 후 4단계 재검증 + 멱등 실행. 모든 지출 단일 경로."""
    result = await _get_executor().execute(body.approved_action, body.proposal)
    return {"result": result.model_dump(mode="json")}


@router.get("/audit")
async def get_audit(approval_id: str):
    """승인 단위 감사 이벤트(append-only) — 게이트 #7 추적용."""
    events = await _AUDIT_LOG.for_approval(approval_id)
    return {
        "events": [
            {
                "event_id": e.event_id,
                "category": e.category,
                "occurred_at": e.occurred_at.isoformat(),
                "payload": e.payload,
            }
            for e in events
        ]
    }


# ── 오가닉 vs 광고 비교 (🅰 comparison 도메인 노출) ──────────────────────
# MockAdPlatform은 get_metrics 미구현(fetch_hourly_metrics만) → ComparisonService가
# 요구하는 단일 스냅샷을 마지막(누적) 시간행으로 공급하는 얇은 어댑터로 우회한다.
# 🅰가 MockAdPlatform.get_metrics를 추가하면 이 어댑터는 제거 가능.
class _MockAdSnapshotReader:
    """하루치 fetch_hourly_metrics의 마지막(누적) 스냅샷을 단일 지표로 반환."""

    def __init__(self, daily_budget_krw: int = DAILY_BUDGET_KRW, seed: int = 42) -> None:
        self._budget = daily_budget_krw
        self._mock = MockAdPlatform(seed=seed)

    async def get_metrics(self, campaign_id: str, since: datetime) -> MetricsSnapshot:
        snaps = await self._mock.fetch_hourly_metrics(campaign_id, since, None, self._budget)
        return snaps[-1]


# 데모 보드 — (게시물 제목, 오가닉 post id, 광고 campaign id, 일예산). 예산 차이로
# 광고 도달이 벌어져 통과/주의/미달이 고루 나오게 구성.
_BOARD_DEMO: tuple[tuple[str, str, str, int], ...] = (
    ("여름 신상 원피스 🌴", "ig_demo_1", "camp_demo_1", 200_000),
    ("브랜드 데일리 룩", "ig_demo_2", "camp_demo_2", 120_000),
    ("신상 액세서리 모음", "ig_demo_3", "camp_demo_3", 40_000),
    ("쿠폰 안내 공지", "ig_demo_4", "camp_demo_4", 15_000),
)


def _today_utc() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


@router.get("/compare")
async def compare_one(post_id: str = "ig_demo_1", campaign_id: str = "camp_demo_1"):
    """단일 오가닉 게시물 ↔ 광고 캠페인 비교 + 🅰 권고 (ComparisonReport).

    제안 생성·집행은 🅱 — 여기는 분석 산출물(상세 리프트 + 권고)만 노출한다.
    """
    report = await build_comparison_service(settings).compare_and_recommend(
        post_id, campaign_id, _today_utc()
    )
    return report.model_dump(mode="json")


@router.get("/compare/board")
async def compare_board():
    """여러 게시물의 오가닉→광고 증분 일괄 검증 + 권고 (B 뷰). reader 공유로 행마다 상이."""
    organic_reader = build_organic_reader(settings)  # 공유 → rng 진행되며 행별 상이
    since = _today_utc()
    rows = []
    for title, post_id, campaign_id, budget in _BOARD_DEMO:
        svc = ComparisonService(organic_reader, _MockAdSnapshotReader(daily_budget_krw=budget))
        report = await svc.compare_and_recommend(post_id, campaign_id, since)
        rows.append(
            {
                "title": title,
                "lift": report.lift.model_dump(mode="json"),
                "recommendation": report.recommendation.model_dump(mode="json"),
            }
        )
    return {"rows": rows}


# ── 캠페인 목록·성과 대시보드 (🅰 reader 영역 데모 노출) ──────────────────
# 백엔드에 "캠페인 목록" 능력이 없어(이름·상태 미보유) 데모 캠페인 상수 + MockAdPlatform로
# 요약/시계열을 합성한다. 실연동 시 reader.list_campaigns로 교체.
_CAMPAIGNS_DEMO: tuple[tuple[str, str, CampaignState, int, FaultMode | None], ...] = (
    ("camp_1", "여름 신상 원피스", CampaignState.ACTIVE, 200_000, None),
    ("camp_2", "브랜드 데일리 룩", CampaignState.ACTIVE, 120_000, FaultMode.BID_LOSS),
    ("camp_3", "신상 액세서리 모음", CampaignState.ACTIVE, 80_000, FaultMode.AUDIENCE_TOO_NARROW),
    ("camp_4", "쿠폰 안내 공지", CampaignState.UNDER_REVIEW, 40_000, FaultMode.REVIEW_DELAY),
    ("camp_5", "봄 시즌오프 마감", CampaignState.ENDED, 60_000, None),
)


async def _campaign_snapshots(
    campaign_id: str, budget: int, fault: FaultMode | None, seed: int
) -> list[MetricsSnapshot]:
    fault_cfg = FaultConfig(mode=fault) if fault is not None else None
    return await MockAdPlatform(seed=seed).fetch_hourly_metrics(
        campaign_id, _today_utc(), fault_cfg, budget
    )


def _campaign_summary(snaps: list[MetricsSnapshot], budget: int) -> dict:
    """누적 스냅샷에서 일간 요약 KPI 산출 — 노출·도달은 누적, 지출·클릭은 시간행 합산."""
    last = snaps[-1]
    impressions = last.cum_impressions
    total_spend = sum(s.spend_krw for s in snaps)
    total_clicks = sum(s.clicks for s in snaps)  # 광고 내 모든 클릭
    total_inline = sum(s.inline_link_clicks for s in snaps)  # 랜딩/링크로 나간 클릭
    # 전환(conversions)은 광고 telemetry에 아직 없어 데모로 합성한다 — 캠페인별 고정 전환율
    # (campaign_id seed로 결정론). CVR = 전환 / 인라인 링크클릭 (사용자 정의).
    conversions = round(total_inline * Random(snaps[0].campaign_id).uniform(0.04, 0.12))
    return {
        "impressions": impressions,
        "reach": last.cum_reach,
        "spend_krw": total_spend,
        "ctr": round(total_clicks / impressions, 5) if impressions else 0.0,
        "cpc_krw": round(total_spend / total_clicks) if total_clicks else 0,
        "cpm_krw": round(total_spend / impressions * 1000) if impressions else 0,
        "conversions": conversions,
        "cvr": round(conversions / total_inline, 5) if total_inline else 0.0,
        "frequency": last.frequency,
        "pacing_pct": round(total_spend / budget * 100, 1) if budget else 0.0,
    }


@router.get("/campaigns")
async def list_campaigns():
    """데모 캠페인 목록 + 캠페인별 성과 요약 (단일 창구 대시보드)."""
    out = []
    for i, (cid, name, state, budget, fault) in enumerate(_CAMPAIGNS_DEMO):
        snaps = await _campaign_snapshots(cid, budget, fault, seed=40 + i)
        out.append(
            {
                "campaign_id": cid,
                "name": name,
                "state": state.value,
                "daily_budget_krw": budget,
                **_campaign_summary(snaps, budget),
            }
        )
    return {"campaigns": out}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(campaign_id: str):
    """캠페인 상세 — 시간별 노출(기대 vs 실측, 이상구간) + 요약 KPI."""
    for i, (cid, name, state, budget, fault) in enumerate(_CAMPAIGNS_DEMO):
        if cid == campaign_id:
            snaps = await _campaign_snapshots(cid, budget, fault, seed=40 + i)
            actual = [s.impressions for s in snaps]
            expected = expected_hourly_impressions(budget)
            return {
                "campaign_id": cid,
                "name": name,
                "state": state.value,
                "daily_budget_krw": budget,
                "expected": [round(e, 1) for e in expected],
                "actual": actual,
                "anomaly_hours": find_anomaly_window(expected, actual),
                "summary": _campaign_summary(snaps, budget),
            }
    raise HTTPException(status_code=404, detail=f"캠페인 없음: {campaign_id}")


# ── 신규 캠페인 생성 제안 (CREATE_CAMPAIGN, Tier 3 — 항상 사람 승인) ────────
# 진단 없이 폼 입력으로 제안을 생산한다(제안 생산 = 🅱 역할). 대상 id가 없어 CampaignConfig를
# evidence_metrics에 싣는다(옵션 A). 승인·실행은 기존 /approve·/execute로 이어진다.
_DEMO_AD_ACCOUNT = "act_demo_001"


class CreateCampaignRequest(BaseModel):
    name: str
    daily_budget_krw: int = Field(ge=1_000)
    run_days: int = Field(ge=1, le=90)
    creative_ad_id: str | None = None


@router.post("/campaigns/create-proposal")
async def create_campaign_proposal(body: CreateCampaignRequest):
    """폼 입력 → CREATE_CAMPAIGN 제안(Tier 3) 패키징. 승인 후 /execute로 생성(기본 DRY_RUN)."""
    now = datetime.now(UTC)
    config = CampaignConfig(
        campaign_id=f"camp_new_{uuid4().hex[:8]}",
        tenant_id=TENANT_ID,
        ad_account_id=_DEMO_AD_ACCOUNT,
        daily_budget_krw=body.daily_budget_krw,
        start_at=now,
        end_at=now + timedelta(days=body.run_days),
        creative_ad_id=body.creative_ad_id,
    )
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=TENANT_ID,
            ad_account_id=_DEMO_AD_ACCOUNT,
            target_object_ids=(_DEMO_AD_ACCOUNT,),  # 신규 — 대상은 광고계정 (옵션 A)
            action_type="CREATE_CAMPAIGN",
            action_tier=ActionTier.TIER_3,
            evidence_metrics={
                "campaign_config": config.model_dump(mode="json"),
                "name": body.name,
            },
            metrics_as_of=now,
            hypothesis="사용자 신규 캠페인 생성 요청",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=0,
            budget_after_krw=body.daily_budget_krw,
            max_total_spend_krw=body.daily_budget_krw * body.run_days,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )
    return {"proposal": proposal.model_dump(mode="json")}


# ── 예산 관리·페이싱 (테넌트 한도 대비 캠페인 합산 소진 + 90/95/100% 판정) ────
# 소진액은 데모 캠페인 지출 합산(레지스트리 커밋분은 데모에서 0). 한도는 _BUDGET에서
# 읽고/쓰며(set_limit, 인메모리), BudgetAuthority.evaluate로 경고 레벨을 판정한다.
async def _budget_status() -> dict:
    spent = 0
    campaigns = []
    for i, (cid, name, _state, budget, fault) in enumerate(_CAMPAIGNS_DEMO):
        snaps = await _campaign_snapshots(cid, budget, fault, seed=40 + i)
        spend = _campaign_summary(snaps, budget)["spend_krw"]
        spent += spend
        campaigns.append({"name": name, "spend_krw": spend})
    limit = _BUDGET.for_tenant(TENANT_ID).limit_krw
    decision = BudgetAuthority(limit_krw=limit, spent_krw=spent).evaluate(0).value
    return {
        "tenant_id": TENANT_ID,
        "limit_krw": limit,
        "spent_krw": spent,
        "remaining_krw": max(limit - spent, 0),
        "ratio": round(spent / limit, 3) if limit else 0.0,
        "decision": decision,
        "thresholds": {"warn": WARN_THRESHOLD, "escalate": ESCALATE_THRESHOLD},
        "campaigns": campaigns,
    }


@router.get("/budget")
async def get_budget():
    """테넌트 예산 한도 대비 캠페인 합산 소진 + 90/95/100% 판정."""
    return await _budget_status()


class BudgetLimitRequest(BaseModel):
    limit_krw: int = Field(ge=0)


@router.post("/budget/limit")
async def set_budget_limit(body: BudgetLimitRequest):
    """예산 한도 설정 — 변경 후 경고 레벨(decision)이 즉시 반영(인메모리)."""
    _BUDGET.set_limit(TENANT_ID, body.limit_krw)
    return await _budget_status()


# ── 시간축 자동 에스컬레이션 (re_evaluate — 엔드포인트·tick·추후 SQS 동일 함수) ────
# 가벼운 조치부터 우선순위대로 시도하고, 회복(원래 anomaly 소멸) 안 되면 다음 단계 제안.
# Tier 3은 항상 건별 승인 — "자동"은 다음 단계 *제안* 자동 생성만 뜻한다(HITL 강제).
_escalation: EscalationController | None = None


def _get_escalation() -> EscalationController:
    global _escalation  # noqa: PLW0603
    if _escalation is None:
        _escalation = EscalationController(
            store=build_escalation_store(settings),
            detector=DemoScenarioDetector(),  # 데모 시나리오 — 2단계 집행 후 회복
            agent=build_regeneration_agent(),  # 키 없으면 결정론 폴백
            audit=_AUDIT_LOG,
        )
    return _escalation


def _now_or(now_iso: str | None) -> datetime:
    """데모 tick — now 미지정이면 현재. 지정 시 그 시각으로 결정론 재평가."""
    return datetime.fromisoformat(now_iso) if now_iso else datetime.now(UTC)


def _escalation_payload(outcome) -> dict:
    return {
        "status": outcome.status.value,
        "reason": outcome.reason,
        "run_id": outcome.run_id,
        "notice": outcome.notice,
        "proposal": outcome.proposal.model_dump(mode="json") if outcome.proposal else None,
    }


class ReEvaluateRequest(BaseModel):
    tenant_id: str = TENANT_ID
    ad_account_id: str = _DEMO_AD_ACCOUNT
    campaign_id: str = CAMPAIGN_ID
    now: str | None = None  # ISO8601 — 데모 tick(시간 전진)


@router.post("/re-evaluate")
async def re_evaluate(body: ReEvaluateRequest):
    """사다리 1회 재평가 — 개시/다음단계 제안 / 보류(PENDING) / 회복 / 소진을 반환."""
    outcome = await _get_escalation().re_evaluate(
        body.tenant_id, body.ad_account_id, body.campaign_id, now=_now_or(body.now)
    )
    return _escalation_payload(outcome)


class RungOutcomeRequest(BaseModel):
    run_id: str
    now: str | None = None
    approval_id: str | None = None


@router.post("/re-evaluate/executed")
async def mark_rung_executed(body: RungOutcomeRequest):
    """현재 단계가 집행됐음을 사다리에 알린다 (다음 재평가에서 회복 판정 가능)."""
    await _get_escalation().on_executed(
        body.run_id, now=_now_or(body.now), approval_id=body.approval_id
    )
    return {"run_id": body.run_id, "rung_status": "executed"}


@router.post("/re-evaluate/rejected")
async def mark_rung_rejected(body: RungOutcomeRequest):
    """현재 단계가 거절됐음을 알린다 (다음 재평가에서 즉시 다음 단계로 에스컬레이션)."""
    await _get_escalation().on_rejected(body.run_id)
    return {"run_id": body.run_id, "rung_status": "rejected"}
