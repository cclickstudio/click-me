"""🤝 매니지먼트 얇은 엔드포인트 — 감지·진단·승인(HITL) 플로우 노출.

오케스트레이터('입')의 소유는 미정(R&R §6) — 본 라우터는 데모용 최소 구현이며
판정 로직은 전부 domain.management(approval.py 등)에 위임한다.
무상태(stateless): 프론트가 받은 제안을 그대로 돌려보내고, proposal_hash 재검증으로
변조를 감지한다 (승인 전 3단계 검증 시연).
"""

import asyncio
import calendar
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from random import Random
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.billing import DEMO_ORG_ID, get_billing_service
from core.auth import get_current_user
from core.config import settings
from core.db import get_db
from core.models import (
    CampaignKpiOverride,
    CreatedCampaign,
    MetaConnection,
    OrganizationMember,
    User,
)
from domain.billing.service.billing_service import BillingError
from domain.management.adapters.generator.client import (
    GeneratorUnavailableError,
    InvalidGenerationError,
)
from domain.management.adapters.meta.client import MetaApiError
from domain.management.adapters.meta.connection_flow import complete_meta_connection
from domain.management.adapters.meta.oauth import build_login_url
from domain.management.adapters.meta.token_crypto import TokenCipher
from domain.management.adapters.mock import MockAdPlatform, MockOrganicReader
from domain.management.agents.outcome import OutcomeKind
from domain.management.agents.regeneration import RemediationContext
from domain.management.agents.regeneration_tools import build_regeneration_agent
from domain.management.approval import (
    approve,
    relabel_if_mismatch,
    requires_human,
    validate_proposal,
)
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult
from domain.management.campaign_policy import get_campaign_policy, min_daily_budget_for
from domain.management.comparison.service.before_after_service import compute_before_after
from domain.management.comparison.service.comparison_service import ComparisonService
from domain.management.contracts.enums import (
    ActionTier,
    CampaignState,
    DiagnosisStatus,
    ExecutionMode,
)
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
    RealOutcome,
    finalize_proposal,
)
from domain.management.conversion_value import estimate_roas
from domain.management.demo import CAMPAIGN_ID, TENANT_ID, build_sample_proposal
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)
from domain.management.detection.performance_dx import diagnose_performance
from domain.management.escalation import EscalationController
from domain.management.escalation_demo import DemoScenarioDetector
from domain.management.execution.executor import DEFAULT_ALLOWED_MODES, Executor
from domain.management.execution.tier import (
    ESCALATE_THRESHOLD,
    WARN_THRESHOLD,
    BudgetAuthority,
    TenantBudgetRegistry,
)
from domain.management.target_check import is_target_missed
from domain.management.wiring import (
    build_audit_sink,
    build_diagnosis_agent,
    build_escalation_store,
    build_generator_client,
    build_idempotency_store,
    build_prediction_reader,
    build_reader,
    build_writer,
)
from tools.storage.s3 import download_bytes

router = APIRouter()

# 멀티테넌트 Meta 연결 요청 스코프 — App Review 승인 권한과 일치해야 한다.
_META_CONNECT_SCOPES = [
    "ads_read",
    "ads_management",
    "instagram_basic",
    "instagram_manage_insights",
    "pages_show_list",
    "pages_read_engagement",
    "leads_retrieval",  # 리드(잠재고객) 명단 조회 — 즉석 양식 제출 데이터 fetch
]

_DEMO_FAULTS = {"bid_loss", "review_rejected", "none"}

# use_mock=True(기본)면 인메모리, False면 DB(idempotency_keys·audit_events) — wiring 분기.
# 예산은 이번 범위 밖이라 인메모리 유지 (후속 B-1.2).
_AUDIT_LOG = build_audit_sink(settings)
_BUDGET = TenantBudgetRegistry(default_limit_krw=10_000_000)
_executor: Executor | None = None


async def _state_version(_ad_account_id: str) -> str:
    return "state_v1"  # 데모 고정 — 제안의 expected_state_version과 일치


def _resolved_execution_mode() -> ExecutionMode:
    """settings 기반 실행 모드 — use_mock이면 무조건 MOCK(봉인).

    실모드(use_mock=False)에서만 management_execution_mode(dry_run|validate_only|live)를 따른다.
    LIVE는 여기를 통해서만 들어오고, 호출부는 /approve 단일 경로(AUTO 자율 승인은 안 거침).
    """
    if getattr(settings, "use_mock", True):
        return ExecutionMode.MOCK
    raw = getattr(settings, "management_execution_mode", "dry_run")
    try:
        return ExecutionMode(raw)
    except ValueError:
        return ExecutionMode.DRY_RUN


def _get_executor() -> Executor:
    global _executor  # noqa: PLW0603
    if _executor is None:
        # LIVE는 명시 opt-in(use_mock=False + mode=live)일 때만 executor 게이트를 통과시킨다.
        allowed = DEFAULT_ALLOWED_MODES
        if _resolved_execution_mode() is ExecutionMode.LIVE:
            allowed = (*DEFAULT_ALLOWED_MODES, ExecutionMode.LIVE)
        _executor = Executor(
            build_writer(settings),
            idempotency=build_idempotency_store(settings),
            audit=_AUDIT_LOG,
            budget_for=_BUDGET.for_tenant,
            state_version_provider=_state_version,
            current_policy_version=APPROVAL_POLICY_VERSION,
            allowed_modes=allowed,
        )
    return _executor


@router.get("/run")
async def run_detection(fault: str = "bid_loss"):
    """감지 사이클 1회 실행: Mock 게재 → 기대 곡선 비교 → 결정론 진단 → 제안 검증."""
    if fault not in _DEMO_FAULTS:
        raise HTTPException(status_code=422, detail=f"fault는 {sorted(_DEMO_FAULTS)} 중 하나")

    fault_cfg = None if fault == "none" else FaultConfig(mode=FaultMode(fault))
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    # 이상감지 데모 = 고장 주입(BID_LOSS 등)이라 항상 MockAdPlatform — 실 reader는 fault를 무시하고
    # 데모 CAMPAIGN_ID가 실 Meta엔 없어 깨진다. 실 캠페인 이상은 /campaigns/{id} 상세에서 본다.
    snapshots = await MockAdPlatform().fetch_hourly_metrics(CAMPAIGN_ID, today, fault_cfg)
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

    action = approve(body.proposal, body.approver_id, execution_mode=_resolved_execution_mode())
    return {"status": "approved", "approved_action": action.model_dump(mode="json")}


class RegenerateRequest(BaseModel):
    diagnosis: DiagnosisResult


@router.post("/regenerate")
async def regenerate(
    body: RegenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """🅱 재생성 agent — 진단 수신 → 4-3 위임 생성 → guard → AWAITING_SELECTION."""
    org_id = await _require_org_id(user, db)
    if body.diagnosis.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 진단으로 재생성할 수 없습니다.")
    ad_account = await _require_ad_account(db, org_id)
    agent = build_regeneration_agent()  # API 키 없으면 결정론 폴백
    context = RemediationContext(
        ad_account_id=ad_account,
        target_object_ids=(body.diagnosis.campaign_id,),
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        run_days=7,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    outcome = await agent.rank(body.diagnosis, context)
    # AWAITING_SELECTION: 자동 선택 금지 — 사람이 고를 수 있도록 후보 목록과 토큰을 그대로 반환.
    if outcome.kind is OutcomeKind.AWAITING_SELECTION:
        return {
            "kind": outcome.kind.value,
            "selection_token": outcome.selection_token,
            "candidates": outcome.candidates,
        }
    # 비크리에이티브 가지(PROPOSED / OBSERVE 등)는 제안 또는 상태를 반환.
    if outcome.kind is OutcomeKind.PROPOSED and outcome.proposal is not None:
        return {"kind": outcome.kind.value, "proposal": outcome.proposal.model_dump(mode="json")}
    raise HTTPException(
        status_code=422,
        detail={"kind": outcome.kind.value, "reason": outcome.reason and outcome.reason.value},
    )


class ExecuteRequest(BaseModel):
    approved_action: ApprovedAction
    proposal: ActionProposal


def _find_in_snapshot(obj: object, key: str) -> object | None:
    """중첩된 결과 스냅샷(dict/list)에서 키를 재귀로 찾는다 (campaign_meta_id 추출용)."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_in_snapshot(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_in_snapshot(v, key)
            if found is not None:
                return found
    return None


async def _record_created_campaign(db: AsyncSession, proposal: ActionProposal, result) -> None:
    """캠페인 생성 결과를 created_campaigns에 누적 기록 — 실패해도 응답엔 영향 없음(best-effort)."""
    cfg = proposal.evidence_metrics.get("campaign_config") or {}
    meta_id = _find_in_snapshot(result.platform_response_snapshot, "campaign_meta_id")
    db.add(
        CreatedCampaign(
            tenant_id=proposal.tenant_id,
            meta_campaign_id=str(meta_id) if meta_id else None,
            name=cfg.get("name") or proposal.evidence_metrics.get("name") or "(이름없음)",
            objective=cfg.get("objective", "traffic"),
            ad_account_id=proposal.ad_account_id,
            daily_budget_krw=int(cfg.get("daily_budget_krw") or proposal.budget_after_krw or 0),
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            execution_mode=str(_resolved_execution_mode().value),
            creative_ad_id=cfg.get("creative_ad_id"),  # 집행 전 시뮬 예측 연결용
        )
    )
    await db.commit()


@router.post("/execute")
async def execute(
    body: ExecuteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """🅱 executor — 승인 후 4단계 재검증 + 멱등 실행. 모든 지출 단일 경로."""
    org_id = await _require_org_id(user, db)
    if body.proposal.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 제안은 실행할 수 없습니다.")
    if body.approved_action.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 승인은 실행할 수 없습니다.")
    result = await _get_executor().execute(body.approved_action, body.proposal)
    if body.proposal.action_type == "CREATE_CAMPAIGN":
        try:
            await _record_created_campaign(db, body.proposal, result)
        except Exception:  # noqa: BLE001 — 적재 실패가 생성 응답을 막지 않게
            await db.rollback()
    response: dict[str, object] = {"result": result.model_dump(mode="json")}
    # 실패면 Meta 사용자용 안내(error_user_msg)를 끌어올려 프론트가 그대로 보여주게 한다.
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    if status != "success":
        msg = _find_in_snapshot(result.platform_response_snapshot, "user_msg")
        if msg:
            response["error_message"] = str(msg)
    return response


@router.get("/created-campaigns")
async def created_campaigns(db: AsyncSession = Depends(get_db)):
    """앱에서 생성한 캠페인 누적 기록 (최신순) — 네온 DB 영속."""
    rows = (
        (await db.execute(select(CreatedCampaign).order_by(CreatedCampaign.created_at.desc())))
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "id": str(r.id),
                "tenant_id": r.tenant_id,
                "meta_campaign_id": r.meta_campaign_id,
                "name": r.name,
                "objective": r.objective,
                "ad_account_id": r.ad_account_id,
                "daily_budget_krw": r.daily_budget_krw,
                "status": r.status,
                "execution_mode": r.execution_mode,
                "created_at": r.created_at.isoformat(),
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
            }
            for r in rows
        ]
    }


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
    비교는 매칭된 오가닉+부스트 쌍이 필요한 데모라 use_mock 무관하게 항상 mock 데이터.
    """
    svc = ComparisonService(MockOrganicReader(), _MockAdSnapshotReader())
    report = await svc.compare_and_recommend(post_id, campaign_id, _today_utc())
    return report.model_dump(mode="json")


@router.get("/compare/board")
async def compare_board():
    """여러 게시물의 오가닉→광고 증분 일괄 검증 + 권고 (B 뷰). 매칭 쌍 데모라 항상 mock."""
    organic_reader = MockOrganicReader()  # 데모 게시물 — 실모드에도 mock(실 Meta엔 해당 ID 없음)
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


@router.get("/compare/before-after")
async def compare_before_after(db: AsyncSession = Depends(get_db)):
    """집행 전(시뮬 예측) vs 후(실측) — 실제 Meta 캠페인별.

    후=실 Meta 실측(list_campaigns→get_metrics→RealOutcome). 전=PredictionReader(지금 Mock 슬롯,
    추후 실 시뮬). 예측·실측 스케일이 달라 환산 없이 나란히 + 정성 판정(compute_before_after).
    예측 링크(creative_ad_id)는 created_campaigns에서 meta_id로 매핑(없으면 시뮬 미연결).
    """
    reader = build_reader(settings)
    pred_reader = build_prediction_reader(settings)
    now = datetime.now(UTC)
    # meta_campaign_id → creative_ad_id 매핑(앱에서 만든 캠페인의 시뮬 연결 키)
    ad_by_meta: dict[str, str] = {}
    try:
        rows = (
            (await db.execute(select(CreatedCampaign).where(CreatedCampaign.deleted_at.is_(None))))
            .scalars()
            .all()
        )
        ad_by_meta = {
            str(r.meta_campaign_id): r.creative_ad_id
            for r in rows
            if r.meta_campaign_id and r.creative_ad_id
        }
    except Exception:  # noqa: BLE001 — 매핑 실패해도 실측은 보여준다
        ad_by_meta = {}
    items: list[dict] = []
    try:
        campaigns = await reader.list_campaigns()
    except MetaApiError as exc:
        # Meta 요청 한도(code 17 등) — "캠페인 없음"으로 오해되지 않게 표면화.
        if exc.is_rate_limited:
            return {"items": [], "rate_limited": "Meta 요청 한도 — 잠시 후 다시 시도하세요."}
        return {"items": []}
    except Exception:  # noqa: BLE001 — 그 외 목록 실패면 빈 결과
        return {"items": []}
    for c in campaigns:
        cid = c.campaign_id
        try:
            actual = _real_outcome(await reader.get_metrics(cid, now), cid, ad_by_meta.get(cid))
        except Exception:  # noqa: BLE001 — 캠페인 1건 실측 실패가 전체를 막지 않게
            continue
        ad_id = ad_by_meta.get(cid)
        prediction = await pred_reader.get_prediction(ad_id) if ad_id else None
        ba = compute_before_after(cid, c.name, prediction, actual)
        items.append(ba.model_dump(mode="json"))
    return {"items": items}


_assistant = None


def _get_assistant() -> Callable[[AskRequest], Awaitable[AskResult]]:
    """매니지먼트 에이전틱 RAG 서브에이전트 — 1회 빌드 후 재사용."""
    global _assistant
    if _assistant is None:
        _assistant = build_management_agent(settings)
    return _assistant


@router.post("/assistant")
async def management_assistant(body: AskRequest):
    """자연어 매니지먼트 질의 → 근거+인용 답변(하이브리드 RAG: 실측 툴 + KB).

    오케스트레이터(채팅)가 `build_management_agent`를 'management 서브에이전트'로 사용.
    """
    result = await _get_assistant()(body)
    return result.model_dump(mode="json")


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
        "clicks": total_clicks,
        "reach": last.cum_reach,
        "spend_krw": total_spend,
        "ctr": round(total_clicks / impressions, 5) if impressions else 0.0,
        "cpc_krw": round(total_spend / total_clicks) if total_clicks else 0,
        "cpm_krw": round(total_spend / impressions * 1000) if impressions else 0,
        "conversions": conversions,
        "cvr": round(conversions / total_inline, 5) if total_inline else 0.0,
        "roas": None,  # 매출(전환 가치) 추적 전 — 측정 불가, 합성 금지
        "frequency": last.frequency,
        "pacing_pct": round(total_spend / budget * 100, 1) if budget else 0.0,
    }


def _real_summary(
    m: MetricsSnapshot,
    budget: int,
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
) -> dict:
    """실 reader 단일 집계 스냅샷 → 대시보드 요약.

    전환 필드가 응답에 있으면 CVR·ROAS까지 실측으로 표시하고, 없으면 합성하지 않는다.
    매출이 측정 안 되는(구매 외) 전환은 ROAS가 None인데, 고객이 전환 가치를 입력하면
    그 통계가치로 ROAS를 추정해 채운다(roas_estimated=True로 '추정' 표기 책임을 넘김).
    target_roas(고객 목표) 입력 시 실제 ROAS가 목표 대비 미달이면 target_missed=True.
    """
    roas = m.roas
    roas_estimated = False
    if roas is None:
        estimated = estimate_roas(m.conversions, conversion_value_krw, m.spend_krw)
        if estimated is not None:
            roas, roas_estimated = estimated, True
    return {
        "impressions": m.impressions,
        "clicks": m.clicks,
        "reach": m.cum_reach,
        "spend_krw": m.spend_krw,
        "ctr": m.ctr,
        "cpc_krw": m.cpc_krw,
        "cpm_krw": m.cpm_krw,
        "conversions": m.conversions,
        "cvr": m.cvr,
        "roas": roas,
        "roas_estimated": roas_estimated,
        "target_roas": target_roas,
        "target_missed": is_target_missed(roas, target_roas),
        "conversion_tracking": m.conversions is not None,
        "frequency": m.frequency,
        "pacing_pct": round(m.spend_krw / budget * 100, 1) if budget else 0.0,
    }


async def _list_campaigns_real(
    conversion_value_krw: int | None = None, target_roas: float | None = None
) -> dict:
    """실연동 — Meta 캠페인 목록 + 캠페인별 실측 요약."""
    reader = build_reader(settings)
    since = _today_utc()
    # 목록·계정 자금 병렬 → 캠페인별 지표 병렬 (순차면 캠페인 수만큼 직렬로 느림)
    infos, funding = await asyncio.gather(
        reader.list_campaigns(),
        reader.get_account_funding(),
    )
    metrics = await asyncio.gather(*(reader.get_metrics(c.campaign_id, since) for c in infos))
    out = []
    any_blocked = False
    for info, m in zip(infos, metrics, strict=True):
        # 게재 차단: 계정 자금 막힘 + 캠페인이 켜져 있는데(ACTIVE) 안 도는 경우
        # (게재 기간 종료 캠페인은 state가 ENDED라 제외 — 충전해도 재개 안 됨)
        blocked = funding.delivery_blocked and info.state == CampaignState.ACTIVE
        any_blocked = any_blocked or blocked
        out.append(
            {
                "campaign_id": info.campaign_id,
                "name": info.name,
                "state": info.state.value,
                "daily_budget_krw": info.daily_budget_krw,
                "ended_at": info.ended_at,
                "delivery_blocked": blocked,
                "block_reason": funding.block_reason if blocked else None,
                **_real_summary(m, info.daily_budget_krw, conversion_value_krw, target_roas),
            }
        )
    return {
        "campaigns": out,
        "source": "live",
        # 계정 배너는 실제로 막힌(진행중) 캠페인이 있을 때만 — 전부 종료면 노이즈라 숨김
        "account_block_reason": funding.block_reason if any_blocked else None,
        # 계정 지갑(돈 개념 분리) — 일일예산과 다른 '실제 충전·지출·잔액'
        "account": {
            "available_balance_krw": funding.available_balance_krw,
            "spend_cap_krw": funding.spend_cap_krw,
            "amount_spent_krw": funding.amount_spent_krw,
        },
    }


async def _campaign_diagnosis(
    reader, campaign_id: str, summary: dict, as_of: datetime
) -> dict | None:
    """성과 미달 진단 — 결정론 판정 후 INCONCLUSIVE면 LLM agent 재판정(키 있을 때).

    additive·best-effort: 신호 조회나 LLM이 실패해도 None 반환 → 상세 화면은 그대로.
    """
    try:
        relevance = await reader.get_relevance_diagnostics(campaign_id)
        dx = diagnose_performance(
            TENANT_ID,
            campaign_id,
            roas=summary.get("roas"),
            target_roas=summary.get("target_roas"),
            as_of=as_of,
            relevance=relevance,
        )
        if dx is None:
            return None
        if dx.status == DiagnosisStatus.INCONCLUSIVE:
            dx = await build_diagnosis_agent(settings)(dx, reader)
    except Exception:  # noqa: BLE001 — 진단은 부가 정보: 실패해도 실데이터 상세는 무영향
        return None
    return {
        "anomaly_type": dx.anomaly_type.value,
        "hypothesis": dx.hypothesis,
        "confidence": dx.confidence,
        "source": dx.source.value,
        "status": dx.status.value,
    }


async def _get_campaign_real(
    campaign_id: str, conversion_value_krw: int | None = None, target_roas: float | None = None
) -> dict:
    """실연동 — 캠페인 상세(시간별 실측 + 기대곡선 + 요약 + 성과 미달 진단)."""
    reader = build_reader(settings)
    today = _today_utc()
    # 독립 호출 3개 병렬 — 순차로 기다리면 토글 펼침이 느림(Meta 왕복 ×3).
    campaigns, snaps, m, daily = await asyncio.gather(
        reader.list_campaigns(),
        reader.fetch_hourly_metrics(campaign_id, today),
        reader.get_metrics(campaign_id, today),
        reader.fetch_daily_metrics(campaign_id),
    )
    info = next((c for c in campaigns if c.campaign_id == campaign_id), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"캠페인 없음: {campaign_id}")
    actual = [s.impressions for s in snaps]
    expected = expected_hourly_impressions(info.daily_budget_krw)
    summary = _real_summary(m, info.daily_budget_krw, conversion_value_krw, target_roas)
    return {
        "campaign_id": info.campaign_id,
        "name": info.name,
        "state": info.state.value,
        "daily_budget_krw": info.daily_budget_krw,
        "expected": [round(e, 1) for e in expected],
        "actual": actual,
        "anomaly_hours": find_anomaly_window(expected, actual) if actual else [],
        "series": daily,
        "summary": summary,
        "diagnosis": await _campaign_diagnosis(reader, campaign_id, summary, m.as_of),
    }


@router.get("/campaigns")
async def list_campaigns(conversion_value_krw: int | None = None, target_roas: float | None = None):
    """캠페인 목록 + 캠페인별 성과 요약 (단일 창구 대시보드).

    use_mock=False면 Meta 실측, True면 데모 합성. CVR은 실모드에선 전환 추적 전까지 None.
    conversion_value_krw(전환 1건 가치) 입력 시 구매 외 전환의 ROAS를 추정해 채운다.
    """
    if not getattr(settings, "use_mock", True):
        try:
            return await _list_campaigns_real(conversion_value_krw, target_roas)
        except MetaApiError as exc:
            # 토큰 만료 등 인증 오류는 화면을 깨지 말고 '재연결 필요'로 안내(빈 목록 + auth_error).
            if exc.is_auth_error:
                return {
                    "campaigns": [],
                    "source": "live",
                    "auth_error": "Meta 연결이 만료됐어요. 토큰 갱신(재연결)이 필요합니다.",
                }
            # Meta 요청 한도(code 17 등) — 일시적. 500으로 깨지 말고 안내(폴링이 곧 복구).
            if exc.is_rate_limited:
                return {
                    "campaigns": [],
                    "source": "live",
                    "rate_limited": "Meta 요청 한도에 일시 도달했어요. 잠시 후 다시 불러옵니다.",
                }
            raise
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
    return {"campaigns": out, "source": "mock"}


def _real_outcome(m: MetricsSnapshot, campaign_id: str, creative_id: str | None) -> RealOutcome:
    """실측 스냅샷 → RealOutcome 계약. 전환 응답이 없으면 None(합성 금지)."""
    return RealOutcome(
        creative_id=creative_id,
        campaign_id=campaign_id,
        impressions=m.impressions,
        reach=m.cum_reach,
        spend_krw=m.spend_krw,
        ctr=m.ctr,
        cpc_krw=m.cpc_krw,
        cpm_krw=m.cpm_krw,
        conversions=m.conversions,
        cvr=m.cvr,
        roas=m.roas,
        as_of=m.as_of,
    )


@router.get("/campaigns/{campaign_id}/outcome")
async def get_campaign_outcome(campaign_id: str, creative_id: str | None = None):
    """집행 후 실측 성과(RealOutcome) — 시뮬 예측 vs 실측 캘리브레이션 소비용 seam.

    wiring 경유라 use_mock=False면 Meta 실측, True면 데모. creative_id는 집행한 크리에이티브
    귀속(생성→집행 경로가 stamp; 없으면 None).
    """
    m = await build_reader(settings).get_metrics(campaign_id, _today_utc())
    return _real_outcome(m, campaign_id, creative_id).model_dump(mode="json")


@router.get("/campaigns/{campaign_id}/platforms")
async def get_campaign_platforms(campaign_id: str):
    """게재 플랫폼별(FB/IG 등) 노출·클릭·지출·도달 분해 (publisher_platform)."""
    rows = await build_reader(settings).get_platform_breakdown(campaign_id, _today_utc())
    return {"platforms": [r.model_dump(mode="json") for r in rows]}


@router.get("/campaigns/{campaign_id}/demographics")
async def get_campaign_demographics(campaign_id: str):
    """연령×성별(age,gender) 노출·클릭·지출·도달 분해."""
    rows = await build_reader(settings).get_demographic_breakdown(campaign_id, _today_utc())
    return {"demographics": [r.model_dump(mode="json") for r in rows]}


@router.get("/campaigns/{campaign_id}/creatives")
async def get_campaign_creatives(campaign_id: str):
    """캠페인 대표 크리에이티브 — 광고 시안 이름·썸네일."""
    rows = await build_reader(settings).get_creatives(campaign_id)
    return {"creatives": [r.model_dump(mode="json") for r in rows]}


# ── 수동 KPI(추정 CVR·ROAS) — 조직 단위 DB 영속 (전환 추적 전 고객 입력값) ──


class KpiOverrideBody(BaseModel):
    cvr: float | None = None  # 전환율 % (수동 추정)
    roas: float | None = None  # 투자수익률 배수 (수동 추정)


async def _resolve_org_id(user: User, db: AsyncSession) -> UUID | None:
    """로그인 사용자의 소속 조직 — 없으면 None."""
    return await db.scalar(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
    )


@router.get("/kpi-overrides")
async def list_kpi_overrides(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """로그인 조직의 캠페인별 수동 KPI(추정 CVR·ROAS) — {campaign_id: {cvr, roas}}."""
    org_id = await _resolve_org_id(user, db)
    if org_id is None:
        return {"overrides": {}}
    rows = (
        await db.scalars(
            select(CampaignKpiOverride).where(CampaignKpiOverride.organization_id == org_id)
        )
    ).all()
    return {
        "overrides": {
            r.campaign_id: {
                **({"cvr": r.cvr} if r.cvr is not None else {}),
                **({"roas": r.roas} if r.roas is not None else {}),
            }
            for r in rows
        }
    }


@router.put("/campaigns/{campaign_id}/kpi-override")
async def put_kpi_override(
    campaign_id: str,
    body: KpiOverrideBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 수동 KPI 저장(업서트). cvr·roas 둘 다 비면 행 삭제(실측으로 복귀)."""
    org_id = await _resolve_org_id(user, db)
    if org_id is None:
        raise HTTPException(409, "소속 조직이 없습니다 — 조직 연결 후 시도하세요.")
    row = await db.scalar(
        select(CampaignKpiOverride).where(
            CampaignKpiOverride.organization_id == org_id,
            CampaignKpiOverride.campaign_id == campaign_id,
        )
    )
    if body.cvr is None and body.roas is None:
        if row is not None:
            await db.delete(row)
            await db.commit()
        return {"campaign_id": campaign_id, "cvr": None, "roas": None}
    if row is None:
        row = CampaignKpiOverride(organization_id=org_id, campaign_id=campaign_id)
        db.add(row)
    row.cvr = body.cvr
    row.roas = body.roas
    row.updated_by = user.id
    await db.commit()
    return {"campaign_id": campaign_id, "cvr": row.cvr, "roas": row.roas}


@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """캠페인 삭제 — 자식 광고세트·광고도 함께. LIVE 모드에서만 실제 Meta 삭제(그 외 무동작).

    적재 기록(created_campaigns)은 지우지 않고 deleted_at만 찍는다(감사 이력 — 만듦→지움 보존).
    """
    writer = build_writer(settings)
    result = await writer.delete_campaign(campaign_id, idem_key=f"del_{campaign_id}")
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    if status == "success":
        try:
            await db.execute(
                update(CreatedCampaign)
                .where(CreatedCampaign.meta_campaign_id == campaign_id)
                .values(deleted_at=func.now())
            )
            await db.commit()
        except Exception:  # noqa: BLE001 — 소프트삭제 실패가 본 응답을 막지 않게
            await db.rollback()
    return {"result": result.model_dump(mode="json")}


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: str, conversion_value_krw: int | None = None, target_roas: float | None = None
):
    """캠페인 상세 — 시간별 노출(기대 vs 실측, 이상구간) + 요약 KPI."""
    if not getattr(settings, "use_mock", True):
        return await _get_campaign_real(campaign_id, conversion_value_krw, target_roas)
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
                "series": await MockAdPlatform().fetch_daily_metrics(cid),
                "summary": _campaign_summary(snaps, budget),
            }
    raise HTTPException(status_code=404, detail=f"캠페인 없음: {campaign_id}")


# ── 신규 캠페인 생성 제안 (CREATE_CAMPAIGN, Tier 3 — 항상 사람 승인) ────────
# 진단 없이 폼 입력으로 제안을 생산한다(제안 생산 = 🅱 역할). 대상 id가 없어 CampaignConfig를
# evidence_metrics에 싣는다(옵션 A). 승인·실행은 기존 /approve·/execute로 이어진다.
_DEMO_AD_ACCOUNT = "act_demo_001"


def _resolve_ad_account() -> str:
    """실모드면 실제 광고계정(.env), 데모면 데모 계정."""
    if not getattr(settings, "use_mock", True) and getattr(settings, "meta_ad_account_id", None):
        return settings.meta_ad_account_id
    return _DEMO_AD_ACCOUNT


def _asset_config(name: str | None = None, image_hash: str | None = None) -> CampaignConfig:
    """업로드·미리보기처럼 캠페인 전 단계에서 ad_account만 필요할 때 쓰는 최소 config."""
    now = datetime.now(UTC)
    return CampaignConfig(
        campaign_id=f"asset_{uuid4().hex[:8]}",
        tenant_id=TENANT_ID,
        ad_account_id=_resolve_ad_account(),
        name=name,
        daily_budget_krw=1,
        start_at=now,
        end_at=now + timedelta(days=1),
        image_hash=image_hash,
    )


class CreateCampaignRequest(BaseModel):
    name: str
    objective: Literal["traffic", "leads"] = "traffic"  # 트래픽(클릭) / 리드(잠재고객)
    daily_budget_krw: int = Field(ge=1)  # 실제 최소는 핸들러가 라이브 정책(Meta floor)으로 검증
    run_days: int = Field(ge=1, le=90)
    creative_ad_id: str | None = None
    image_hash: str | None = None  # /ad-image 업로드 결과 — 광고 소재 이미지
    # Meta 타겟·정책 — 폼 입력(단일값) → CampaignConfig로 매핑.
    special_ad_category: Literal[
        "NONE", "HOUSING", "EMPLOYMENT", "CREDIT", "ISSUES_ELECTIONS_POLITICS"
    ] = "NONE"
    country: str = "KR"  # ISO2
    age_min: int = Field(default=18, ge=18, le=65)  # Meta 최소 연령 18
    age_max: int = Field(default=65, ge=18, le=65)
    gender: Literal["all", "male", "female"] = "all"


@router.get("/campaign-policy")
async def campaign_policy():
    """캠페인 생성 정책 — 최소 일예산(Meta 실시간)·특별광고카테고리·연령. 폼이 동적 검증에 사용."""
    return await get_campaign_policy(build_reader(settings))


# 미리보기 포맷 — 페이스북 피드 + 인스타그램(자동 배치라 둘 다 노출됨).
_PREVIEW_FORMATS = ["MOBILE_FEED_STANDARD", "INSTAGRAM_STANDARD"]


@router.post("/ad-image")
async def upload_ad_image(file: UploadFile = File(...)):
    """광고 소재 이미지를 Meta(/adimages)에 업로드 → image_hash 반환. 무과금(자산 등록)."""
    writer = build_writer(settings)
    data = await file.read()
    image_hash = await writer.upload_image(
        _asset_config(), data, file.filename or "ad.jpg", idem_key=f"img_{uuid4().hex[:8]}"
    )
    if not image_hash:
        raise HTTPException(status_code=422, detail="이미지 업로드 실패 — 실모드(live)에서만 가능.")
    return {"image_hash": image_hash}


class AdPreviewRequest(BaseModel):
    image_hash: str
    name: str | None = None


@router.post("/ad-preview")
async def ad_preview(body: AdPreviewRequest):
    """샘플 시안 — 업로드 이미지로 FB 피드·인스타 미리보기(Meta 호스팅 iframe). 무과금(읽기)."""
    writer = build_writer(settings)
    page_id = getattr(settings, "meta_page_id", None)
    if not page_id:
        raise HTTPException(status_code=422, detail="META_PAGE_ID 미설정 — 미리보기 불가.")
    previews = await writer.generate_previews(
        _asset_config(name=body.name), body.image_hash, _PREVIEW_FORMATS, page_id=page_id
    )
    return {"previews": previews}


@router.post("/campaigns/create-proposal")
async def create_campaign_proposal(
    body: CreateCampaignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """폼 입력 → CREATE_CAMPAIGN 제안(Tier 3) 패키징."""
    org_id = await _require_org_id(user, db)
    # Meta 최소 일예산 정책 — Meta에서 실시간 조회(자동 최신화). 미달이면 광고세트 거부 전 차단.
    policy = await get_campaign_policy(build_reader(settings))
    min_budget = min_daily_budget_for(body.objective, policy)
    if body.daily_budget_krw < min_budget:
        raise HTTPException(
            status_code=422,
            detail=f"{body.objective} 캠페인의 최소 일예산은 ₩{min_budget:,}입니다 (Meta 정책).",
        )
    now = datetime.now(UTC)
    ad_account = await _require_ad_account(db, org_id)
    tenant_id = str(org_id)
    # 폼 단일값 → Meta 타겟 코드로 매핑.
    genders = {"all": (), "male": (1,), "female": (2,)}[body.gender]
    categories = () if body.special_ad_category == "NONE" else (body.special_ad_category,)
    config = CampaignConfig(
        campaign_id=f"camp_new_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ad_account_id=ad_account,
        name=body.name,
        objective=body.objective,
        daily_budget_krw=body.daily_budget_krw,
        start_at=now,
        end_at=now + timedelta(days=body.run_days),
        creative_ad_id=body.creative_ad_id,
        image_hash=body.image_hash,
        special_ad_categories=categories,
        countries=(body.country,),
        age_min=body.age_min,
        age_max=body.age_max,
        genders=genders,
    )
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            ad_account_id=ad_account,
            target_object_ids=(ad_account,),  # 신규 — 대상은 광고계정 (옵션 A)
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


class FromCandidateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # self-call URL 경로에 박히므로 안전 문자만 — 경로 주입(../ 등) 차단.
    generation_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    candidate_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    link_url: HttpUrl | None = None
    name: str
    daily_budget_krw: int = Field(ge=1)
    run_days: int = Field(ge=1, le=90)
    special_ad_category: Literal[
        "NONE", "HOUSING", "EMPLOYMENT", "CREDIT", "ISSUES_ELECTIONS_POLITICS"
    ] = "NONE"
    country: str = "KR"
    age_min: int = Field(default=18, ge=18, le=65)
    age_max: int = Field(default=65, ge=18, le=65)
    gender: Literal["all", "male", "female"] = "all"


def _resolve_link_url(req_url: HttpUrl | None) -> str | None:
    """목적지 URL — 요청값만 사용(없으면 None→422). 조직 기본값 prefill은 프론트 담당(스펙 §5.1)."""
    return str(req_url) if req_url is not None else None


@router.post("/campaign-proposals/from-candidate")
async def from_candidate(
    body: FromCandidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """generator 후보 → CREATE_CAMPAIGN(traffic) 제안. 승인·집행은 /approve·/execute 재사용."""
    client = build_generator_client(settings)
    try:
        cand = await client.get_candidate(body.generation_id, body.candidate_id)
    except InvalidGenerationError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.detail) from exc
    except GeneratorUnavailableError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    link_url = _resolve_link_url(body.link_url)
    if not link_url:
        raise HTTPException(status_code=422, detail="목적지 URL(link_url)이 필요합니다.")

    try:
        image_bytes = await download_bytes(cand.s3_key)
    except Exception as exc:  # noqa: BLE001 — S3 유실/손상은 입력 문제로 거부
        raise HTTPException(status_code=422, detail="후보 이미지를 읽을 수 없습니다.") from exc

    writer = build_writer(settings)
    image_hash = await writer.upload_image(
        _asset_config(name=body.name),
        image_bytes,
        "candidate.png",
        idem_key=f"img_{uuid4().hex[:8]}",
    )
    if not getattr(settings, "use_mock", True) and not image_hash:
        raise HTTPException(status_code=502, detail="Meta 이미지 업로드 실패.")

    policy = await get_campaign_policy(build_reader(settings))
    min_budget = min_daily_budget_for("traffic", policy)
    if body.daily_budget_krw < min_budget:
        raise HTTPException(status_code=422, detail=f"최소 일예산은 ₩{min_budget:,}입니다.")

    now = datetime.now(UTC)
    org_id = await _require_org_id(user, db)
    ad_account = await _require_ad_account(db, org_id)
    tenant_id = str(org_id)
    genders = {"all": (), "male": (1,), "female": (2,)}[body.gender]
    categories = () if body.special_ad_category == "NONE" else (body.special_ad_category,)
    config = CampaignConfig(
        campaign_id=f"camp_cand_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ad_account_id=ad_account,
        name=body.name,
        objective="traffic",
        daily_budget_krw=body.daily_budget_krw,
        start_at=now,
        end_at=now + timedelta(days=body.run_days),
        image_hash=image_hash,
        headline=cand.copy.headline,
        body=cand.copy.body,
        link_url=link_url,
        special_ad_categories=categories,
        countries=(body.country,),
        age_min=body.age_min,
        age_max=body.age_max,
        genders=genders,
    )
    snapshot = {
        "generation_id": body.generation_id,
        "candidate_id": cand.candidate_id,
        "copy": cand.copy.model_dump(),
        "s3_key": cand.s3_key,
        "image_hash": image_hash,
        "strategy": cand.strategy,
        "template_id": cand.template_id,
        "idx": cand.idx,
    }
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            ad_account_id=ad_account,
            target_object_ids=(ad_account,),
            action_type="CREATE_CAMPAIGN",
            action_tier=ActionTier.TIER_3,
            evidence_metrics={
                "campaign_config": config.model_dump(mode="json"),
                "name": body.name,
                "candidate_snapshot": snapshot,
            },
            metrics_as_of=now,
            hypothesis="후보 기반 신규 캠페인",
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


# ── 게재 시작(활성화) + 크레딧 연동 + 소진 동기화 ──────────────────────────
# 결제(/billing) 충전 크레딧을 게이트·차감의 단일 한도로 쓴다. Meta 직접 충전은 불가하므로
# 충전액을 캠페인 spend_cap으로 걸어 "그만큼만 집행 → 소진 시 자동 종료"를 동일하게 구현한다.
def _serving_causes(detail, funding) -> tuple[bool, list[dict]]:
    """effective_status·심사·계정 자금을 게재 불가 원인 목록으로 — 한국어 단일 매핑."""
    status = (getattr(detail, "effective_status", "") or "").upper()
    serving = status == "ACTIVE"
    causes: list[dict] = []
    if status in ("DISAPPROVED", "WITH_ISSUES", "AD_DISAPPROVED"):
        issues = getattr(detail, "issues_info", ()) or ()
        msg = "; ".join(issues) if issues else "광고가 심사에서 거부되었습니다."
        causes.append({"code": "DISAPPROVED", "message": f"심사 거부 — {msg}"})
    elif status == "PENDING_REVIEW":
        causes.append(
            {"code": "PENDING_REVIEW", "message": "심사 대기 중입니다 — 검토 후 자동 게재됩니다."}
        )
    elif status in ("PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED"):
        causes.append(
            {"code": "PAUSED", "message": "일시중지 상태입니다 — '게재 시작'으로 활성화하세요."}
        )
    elif not serving and status:
        causes.append({"code": status, "message": f"현재 상태: {status} — 게재되지 않습니다."})
    if funding is not None and getattr(funding, "delivery_blocked", False):
        reason = getattr(funding, "block_reason", None) or "Meta 계정 결제수단을 확인하세요."
        causes.append({"code": "ACCOUNT_FUNDING", "message": reason})
    return serving, causes


class ActivateRequest(BaseModel):
    commit_krw: int | None = Field(
        default=None, ge=1
    )  # 이 캠페인에 배정(=spend_cap). 미지정 시 일예산.
    org_id: str = DEMO_ORG_ID


async def _created_campaign_row(db: AsyncSession, campaign_id: str) -> CreatedCampaign | None:
    return (
        (
            await db.execute(
                select(CreatedCampaign).where(CreatedCampaign.meta_campaign_id == campaign_id)
            )
        )
        .scalars()
        .first()
    )


def _is_demo_campaign(campaign_id: str) -> bool:
    """campaign_id가 데모 픽스처(_CAMPAIGNS_DEMO)에 존재하는지."""
    return any(cid == campaign_id for cid, *_ in _CAMPAIGNS_DEMO)


async def _require_org_id(user: User, db: AsyncSession) -> UUID:
    """로그인 사용자의 소속 org — 없으면 409."""
    org_id = await _resolve_org_id(user, db)
    if org_id is None:
        raise HTTPException(409, "소속 조직이 없습니다 — 조직 연결 후 시도하세요.")
    return org_id


async def _require_owned_campaign(
    db: AsyncSession, org_id: UUID, campaign_id: str
) -> CreatedCampaign | None:
    """DB 적재 캠페인은 tenant 소유 검증.

    DB 행 없음은 mock/demo fixture로 확인된 경우에만 None 허용.
    """
    row = await _created_campaign_row(db, campaign_id)
    if row is not None:
        if row.tenant_id != str(org_id):
            raise HTTPException(403, "다른 조직의 캠페인입니다.")
        return row
    if getattr(settings, "use_mock", True) and _is_demo_campaign(campaign_id):
        return None
    raise HTTPException(404, "캠페인을 찾을 수 없습니다.")


async def _require_ad_account(db: AsyncSession, org_id: UUID) -> str:
    """org의 Meta 광고계정 — 연결에서 도출. live 미연결이면 데모 폴백 금지(fail-closed)."""
    conn = await db.scalar(select(MetaConnection).where(MetaConnection.organization_id == org_id))
    if conn is not None and conn.ad_account_id:
        return conn.ad_account_id
    if getattr(settings, "use_mock", True):
        return _DEMO_AD_ACCOUNT
    raise HTTPException(409, "Meta 광고계정 연결이 필요합니다 — 연결 후 시도하세요.")


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str, body: ActivateRequest, db: AsyncSession = Depends(get_db)
):
    """게재 시작 — Meta 선불 잔액 게이트 → spend_cap → 캠페인·세트·광고 ACTIVE. 실과금 시작점."""
    row = await _created_campaign_row(db, campaign_id)
    commit = body.commit_krw or (row.daily_budget_krw if row else 0)
    if commit <= 0:
        raise HTTPException(status_code=422, detail="배정 금액(commit_krw)을 결정할 수 없습니다.")

    # 1) 게이트 — Meta 광고계정 선불 잔액이 배정액보다 적으면 차단(예산·게재 기준 통일).
    try:
        funding = await build_reader(settings).get_account_funding()
        meta_balance = funding.available_balance_krw or 0
    except Exception:  # noqa: BLE001 — 자금 조회 실패 시 0으로 보아 차단(안전)
        meta_balance = 0
    if meta_balance < commit:
        return {
            "serving": False,
            "result": None,
            "balance_krw": meta_balance,
            "commit_krw": commit,
            "causes": [
                {
                    "code": "INSUFFICIENT_META_BALANCE",
                    "message": (
                        f"Meta 광고계정 선불 잔액 부족 — {commit - meta_balance:,}원 더 필요. "
                        "Ads Manager 결제 설정에서 충전하세요."
                    ),
                    "need_krw": commit - meta_balance,
                    "balance_krw": meta_balance,
                    "commit_krw": commit,
                }
            ],
        }

    # 2) 지출 상한 — 충전액만큼만 집행되도록(소진 시 자동 종료). 실패 시 활성화 중단(무한집행 방지).
    writer = build_writer(settings)
    cap = await writer.set_spend_cap(campaign_id, commit, idem_key=f"cap_{uuid4().hex[:8]}")
    cap_status = cap.status.value if hasattr(cap.status, "value") else str(cap.status)
    if cap_status != "success":
        msg = _find_in_snapshot(cap.platform_response_snapshot, "user_msg")
        return {
            "serving": False,
            "result": cap.model_dump(mode="json"),
            "balance_krw": meta_balance,
            "commit_krw": commit,
            "causes": [
                {
                    "code": "SPEND_CAP_FAILED",
                    "message": str(msg)
                    if msg
                    else "지출 상한 설정 실패 — Meta 최소 상한을 확인하세요.",
                }
            ],
        }

    # 3) 활성화 제안 → 승인 → 실행 (멱등·감사 단일 경로). 버튼 클릭 = Tier 3 사람 승인.
    now = datetime.now(UTC)
    ad_account = _resolve_ad_account()
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=TENANT_ID,
            ad_account_id=ad_account,
            target_object_ids=(campaign_id,),
            action_type="ACTIVATE_CAMPAIGN",
            action_tier=ActionTier.TIER_3,
            evidence_metrics={"commit_krw": commit, "name": row.name if row else campaign_id},
            metrics_as_of=now,
            hypothesis="사용자 게재 시작 요청",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=0,
            budget_after_krw=commit,
            max_total_spend_krw=commit,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )
    action = approve(proposal, "user_demo", execution_mode=_resolved_execution_mode())
    result = await _get_executor().execute(action, proposal)
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    serving = status == "success"
    if serving and row is not None:
        row.status = "active"
        await db.commit()

    resp: dict[str, object] = {
        "serving": serving,
        "result": result.model_dump(mode="json"),
        "balance_krw": meta_balance,
        "commit_krw": commit,
        "causes": [],
    }
    if not serving:
        msg = _find_in_snapshot(result.platform_response_snapshot, "user_msg")
        if msg:
            resp["error_message"] = str(msg)
    return resp


@router.get("/campaigns/{campaign_id}/delivery-status")
async def delivery_status(campaign_id: str):
    """게재 여부 + 불가 원인 + Meta 선불 잔액 — 대시보드/게재 화면이 원인을 그대로 표시."""
    reader = build_reader(settings)
    detail = await reader.get_delivery_status_detail(campaign_id)
    try:
        funding = await reader.get_account_funding()
    except Exception:  # noqa: BLE001 — 자금 조회 실패가 상태 표시를 막지 않게
        funding = None
    try:
        spend_cap = await reader.get_spend_cap(campaign_id)
    except Exception:  # noqa: BLE001 — 상한 조회 실패가 상태 표시를 막지 않게
        spend_cap = None
    serving, causes = _serving_causes(detail, funding)
    # 게재 기준과 통일 — 잔액은 Meta 선불 가용 잔액.
    balance = (funding.available_balance_krw or 0) if funding is not None else 0
    return {
        "campaign_id": campaign_id,
        "serving": serving,
        "effective_status": detail.effective_status,
        "issues": list(getattr(detail, "issues_info", ()) or ()),
        "causes": causes,
        "spend_cap_krw": spend_cap,
        "balance_krw": balance,
    }


@router.get("/campaigns/{campaign_id}/sync")
async def sync_campaign(
    campaign_id: str, org_id: str = DEMO_ORG_ID, db: AsyncSession = Depends(get_db)
):
    """Meta 누적 소진액 → 크레딧 차감 정산(증분) + 자동 종료 상태 반영."""
    reader = build_reader(settings)
    billing = get_billing_service()
    metrics = await reader.get_metrics(campaign_id, datetime.now(UTC))
    spent = max(0, metrics.spend_krw or 0)
    already = await billing.spent_for(org_id, campaign_id)
    charged = 0
    delta = spent - already
    if delta > 0:
        amount = min(delta, await billing.balance(org_id))  # 잔액 한도 내에서만(음수 잔액 금지)
        if amount > 0:
            try:
                await billing.record_spend(org_id, amount, ref_id=campaign_id)
                charged = amount
            except BillingError:
                charged = 0
    detail = await reader.get_delivery_status_detail(campaign_id)
    ended = (detail.effective_status or "").upper() not in ("ACTIVE", "PENDING_REVIEW")
    row = await _created_campaign_row(db, campaign_id)
    if row is not None:
        new_status = "ended" if ended else "active"
        if row.status != new_status:
            row.status = new_status
            await db.commit()
    return {
        "campaign_id": campaign_id,
        "spend_krw": spent,
        "charged_now_krw": charged,
        "balance_krw": await billing.balance(org_id),
        "effective_status": detail.effective_status,
        "ended": ended,
    }


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, db: AsyncSession = Depends(get_db)):
    """캠페인 즉시 일시중지(PAUSED) — 게재·과금 중단. 크레딧 게이트 불요(돈이 나가는 쪽 아님)."""
    now = datetime.now(UTC)
    ad_account = _resolve_ad_account()
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=TENANT_ID,
            ad_account_id=ad_account,
            target_object_ids=(campaign_id,),
            action_type="PAUSE_CAMPAIGN",
            action_tier=ActionTier.TIER_1,
            evidence_metrics={"name": campaign_id},
            metrics_as_of=now,
            hypothesis="사용자 일시중지 요청",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=0,
            budget_after_krw=0,
            max_total_spend_krw=0,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )
    action = approve(proposal, "user_demo", execution_mode=_resolved_execution_mode())
    result = await _get_executor().execute(action, proposal)
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    if status == "success":
        try:
            await db.execute(
                update(CreatedCampaign)
                .where(CreatedCampaign.meta_campaign_id == campaign_id)
                .values(status="paused")
            )
            await db.commit()
        except Exception:  # noqa: BLE001 — 상태 기록 실패가 응답을 막지 않게
            await db.rollback()
    resp: dict[str, object] = {
        "paused": status == "success",
        "result": result.model_dump(mode="json"),
    }
    if status != "success":
        msg = _find_in_snapshot(result.platform_response_snapshot, "user_msg")
        if msg:
            resp["error_message"] = str(msg)
    return resp


@router.get("/campaigns/{campaign_id}/leads")
async def campaign_leads(campaign_id: str):
    """이 캠페인 광고로 제출된 잠재고객(리드) 명단 — Meta leadgen에서 조회.

    리드 데이터는 Meta에 저장된다(우리 도메인 아님). 페이지 토큰 + leads_retrieval 권한이
    필요하며, 권한·토큰 문제는 note로 안내한다(빈 목록 반환, 화면이 안 깨지게).
    """
    if getattr(settings, "use_mock", True):
        return {"leads": [], "count": 0, "note": "데모(mock) 모드 — 리드는 live에서 조회됩니다."}
    from domain.management.adapters.meta.client import (  # noqa: PLC0415 — live 전용 지연 로드
        MetaClient,
        build_meta_client,
    )

    client = build_meta_client(settings)
    page_id = str(getattr(settings, "meta_page_id", "") or "")
    try:
        # 사용자 토큰 → 페이지 토큰 (leadgen 리드 조회는 페이지 토큰 필요)
        accts = await client.get("me/accounts", {"fields": "id,access_token", "limit": 100})
        page_token = next(
            (p.get("access_token") for p in accts.get("data", []) if str(p.get("id")) == page_id),
            None,
        )
        if not page_token:
            return {"leads": [], "count": 0, "note": "페이지 토큰을 얻지 못함(페이지 권한 확인)."}
        page_client = MetaClient(
            page_token, api_version=getattr(settings, "meta_graph_api_version", None) or "v21.0"
        )
        # 캠페인 하위 광고 → 광고별 리드 수집
        ads = await client.get(f"{campaign_id}/ads", {"fields": "id", "limit": 200})
        leads: list[dict] = []
        for ad in ads.get("data", []):
            res = await page_client.get(
                f"{ad['id']}/leads", {"fields": "created_time,field_data", "limit": 200}
            )
            for lead in res.get("data", []):
                fields = {
                    f.get("name"): (f.get("values") or [""])[0]
                    for f in (lead.get("field_data") or [])
                }
                leads.append({"created_time": lead.get("created_time"), "fields": fields})
        leads.sort(key=lambda x: x.get("created_time") or "", reverse=True)
        return {"leads": leads, "count": len(leads)}
    except MetaApiError as exc:
        # 권한 부족(leads_retrieval 미승인)·토큰 문제 등 — 화면용 안내로 변환.
        return {"leads": [], "count": 0, "note": f"리드 조회 불가: {exc.user_msg or exc.message}"}


# ── 예산 관리·페이싱 (테넌트 한도 대비 캠페인 합산 소진 + 90/95/100% 판정) ────
# 소진액은 데모 캠페인 지출 합산(레지스트리 커밋분은 데모에서 0). 한도는 _BUDGET에서
# 읽고/쓰며(set_limit, 인메모리), BudgetAuthority.evaluate로 경고 레벨을 판정한다.
async def _budget_status() -> dict:
    # 실모드: 한도=총 충전 크레딧, 소진=실 Meta 집행액, 잔여=크레딧 잔액.
    if not getattr(settings, "use_mock", True):
        return await _budget_status_live()
    # 데모(mock): 합성 캠페인 지출 + 인메모리 한도.
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


async def _budget_status_live() -> dict:
    """실데이터 예산 현황 — 월 목표 예산 대비 이번 달 실소진 페이싱(관제).

    한도=월 목표 예산(설정), 소진=이번 달 Meta 집행, 잔여=목표−소진, 여력=Meta 선불 잔액.
    런레이트(projection)로 "이 페이스면 월말 얼마"를 예측한다. 캠페인별은 이번 달 소진·ROAS.
    """
    reader = build_reader(settings)
    now = datetime.now(UTC)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    target = _BUDGET.for_tenant(TENANT_ID).limit_krw  # 월 목표(미설정 0) — v1 in-memory

    # 이번 달 실소진(계정 단위 1콜) + 일자별 곡선
    try:
        spent = await reader.get_account_spend("this_month")
    except Exception:  # noqa: BLE001 — 조회 실패면 0
        spent = 0
    try:
        daily = await reader.get_account_daily_spend("this_month")
    except Exception:  # noqa: BLE001
        daily = []
    # 여력 — Meta 선불 가용 잔액
    try:
        account_balance = (await reader.get_account_funding()).available_balance_krw or 0
    except Exception:  # noqa: BLE001
        account_balance = 0
    # 캠페인별 이번 달 소진 + ROAS
    campaigns: list[dict] = []
    try:
        for c in await reader.list_campaigns():
            try:
                m = await reader.get_metrics(c.campaign_id, now, date_preset="this_month")
                campaigns.append({"name": c.name, "spend_krw": m.spend_krw or 0, "roas": m.roas})
            except Exception:  # noqa: BLE001 — 캠페인 1건 실패가 전체를 막지 않게
                campaigns.append({"name": c.name, "spend_krw": 0, "roas": None})
    except Exception:  # noqa: BLE001
        campaigns = []

    # 런레이트 예측 — 현재 페이스로 월말 예상 소진.
    projection = round(spent / now.day * days_in_month) if now.day and spent else spent
    decision = (
        BudgetAuthority(limit_krw=target, spent_krw=spent).evaluate(0).value
        if target > 0
        else "allow"
    )
    return {
        "tenant_id": TENANT_ID,
        "limit_krw": target,
        "monthly_target_krw": target,
        "spent_krw": spent,
        "remaining_krw": max(target - spent, 0),
        "ratio": round(spent / target, 3) if target else 0.0,
        "projection_krw": projection,
        "account_balance_krw": account_balance,
        "period": now.strftime("%Y-%m"),
        "daily": daily,
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


# ── 멀티테넌트 Meta 연결 (OAuth) — 외부 광고주가 자기 Meta 자산을 연결 ──
# organization_id는 임시로 쿼리/state로 운반 — JWT 연동 시 토큰의 org로 대체한다.


@router.get("/meta/connect")
async def meta_connect(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """로그인한 광고주의 조직(JWT)으로 Facebook 로그인 URL을 만들어 반환한다.

    브라우저 최상위 이동엔 Authorization 헤더가 안 실리므로, 프론트가 이 인증된 XHR로
    login_url을 받아 window.location으로 이동시킨다. org는 state로 콜백까지 운반.
    """
    app_id = getattr(settings, "meta_app_id", None)
    if not app_id:
        raise HTTPException(503, "META_APP_ID 미설정 — Meta 연결 불가")
    org_id = await db.scalar(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
    )
    if org_id is None:
        raise HTTPException(409, "소속 조직이 없습니다 — 조직 연결 후 시도하세요.")
    state = f"{org_id}:{uuid4().hex}"  # org 운반 + CSRF nonce
    url = build_login_url(
        app_id=app_id,
        redirect_uri=str(request.url_for("meta_callback")),
        scopes=_META_CONNECT_SCOPES,
        state=state,
        api_version=settings.meta_graph_api_version,
    )
    return {"login_url": url, "state": state}


@router.get("/meta/callback", name="meta_callback")
async def meta_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """OAuth 콜백(브라우저 리다이렉트) — code를 장기 토큰으로 교환해 org 연결로 암호화 저장.

    동의 취소·에러·code 누락이면 raw 422 대신 연동 페이지로 안내 리다이렉트한다.
    성공/취소 모두 프론트 주소(frontend_base_url)로 보내 화면이 깔끔히 뜨게 한다.
    """
    front = settings.frontend_base_url.rstrip("/")
    # 동의 취소/에러/필수값 누락 → 연동 페이지로 친절히 (영상에 raw 에러 안 뜨게)
    if error or not code or not state:
        return RedirectResponse(f"{front}/manage/connect?meta=cancelled", status_code=303)
    key = getattr(settings, "meta_token_encryption_key", None)
    app_id = getattr(settings, "meta_app_id", None)
    app_secret = getattr(settings, "meta_app_secret", None)
    if not key:
        raise HTTPException(503, "토큰 암호화 키(META_TOKEN_ENCRYPTION_KEY) 미설정")
    if not (app_id and app_secret):
        raise HTTPException(503, "META_APP_ID/META_APP_SECRET 미설정")
    org = state.split(":", 1)[0]  # connect가 넣은 org:nonce
    await complete_meta_connection(
        db,
        TokenCipher.from_base64_key(key),
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=str(request.url_for("meta_callback")),
        code=code,
        organization_id=uuid4_or_str(org),
        api_version=settings.meta_graph_api_version,
    )
    return RedirectResponse(f"{front}/manage/connect?meta=connected", status_code=303)


def uuid4_or_str(value: str):
    """org 식별자를 UUID로 변환(데모용 비-UUID 문자열이면 그대로 반환)."""
    try:
        return UUID(value)
    except ValueError:
        return value
