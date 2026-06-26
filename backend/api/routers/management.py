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
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, StreamingResponse
from langsmith import traceable
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.billing import DEMO_ORG_ID, get_billing_service
from core.auth import (
    get_current_user,
    optional_user,
    require_user_org,
    user_org_id,
)
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
from domain.management.adapters.meta.connection_repository import MetaConnectionRepository
from domain.management.adapters.meta.credentials import MetaCredentials
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
from domain.management.comparison.calibration import CalibrationAnchor, build_summary
from domain.management.comparison.service.before_after_service import compute_before_after
from domain.management.comparison.service.comparison_service import ComparisonService
from domain.management.contracts.enums import (
    ActionTier,
    CampaignState,
    DiagnosisStatus,
    ExecutionMode,
)
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.platform import AdPlatformReader, AdPlatformWriter
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
from domain.management.escalation import EscalationController, EscalationRun
from domain.management.escalation_demo import DemoScenarioDetector
from domain.management.execution.assistant_tools import execution_history
from domain.management.execution.executor import DEFAULT_ALLOWED_MODES, Executor
from domain.management.execution.regeneration_jobs import (
    CandidateNotInJob,
    JobNotAwaitingSelection,
    JobNotFound,
    JobTenantMismatch,
    SelectionContextExpired,
)
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
    build_regeneration_job_service,
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


# ── 멀티테넌시: 요청 단위 org 스코프 리더/라이터 의존성 ──────────────────────
# mock 모드는 무인증·전역 mock 유지(테스트·데모 보존). live는 로그인 org의 Meta 연결
# (토큰·계정)로만 동작 — 남의 전역 계정 노출 금지. 실제 자격증명 해석은 아래 _require_reader/
# _require_writer(파일 뒤편, 런타임 호출)에서 한다.
# 선택적 인증·org 해석은 core.auth 공용 함수 사용(라우터 복붙 제거 — 한 곳에서 규칙 변경).
_optional_user = optional_user


async def _request_reader(
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
) -> AdPlatformReader:
    """요청 단위 리더 — mock이면 전역 mock(무인증), live면 로그인 org 연결 기반(미연결 409)."""
    if getattr(settings, "use_mock", True):
        return build_reader(settings)
    if user is None:
        raise HTTPException(401, "인증 토큰이 없습니다.")
    return await _require_reader(db, await _require_org_id(user, db))


async def _request_writer(
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
) -> AdPlatformWriter:
    """요청 단위 라이터 — mock이면 전역 DRY_RUN(무인증), live면 로그인 org 연결 기반(미연결 409)."""
    if getattr(settings, "use_mock", True):
        return build_writer(settings)
    if user is None:
        raise HTTPException(401, "인증 토큰이 없습니다.")
    return await _require_writer(db, await _require_org_id(user, db))


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


def _is_sending_mode() -> bool:
    """실제 Meta 전송이 일어나는 모드 — 이미지 업로드 등 실 호출 결과를 검증할 대상.

    DRY_RUN/MOCK은 upload_image가 None을 반환(미전송, 의도된 동작)이라 image_hash 부재가 정상.
    """
    return _resolved_execution_mode() in (ExecutionMode.VALIDATE_ONLY, ExecutionMode.LIVE)


def _get_executor(writer=None) -> Executor:
    global _executor  # noqa: PLW0603
    # LIVE는 명시 opt-in(use_mock=False + mode=live)일 때만 executor 게이트를 통과시킨다.
    allowed = DEFAULT_ALLOWED_MODES
    if _resolved_execution_mode() is ExecutionMode.LIVE:
        allowed = (*DEFAULT_ALLOWED_MODES, ExecutionMode.LIVE)
    if writer is not None:
        # org 스코프(라이브) — org 연결 writer로 매 요청 새 executor. 멱등은 DB-백이라 무상태,
        # 전역 싱글턴을 오염시키지 않는다(멀티테넌시 정합).
        return Executor(
            writer,
            idempotency=build_idempotency_store(settings),
            audit=_AUDIT_LOG,
            budget_for=_BUDGET.for_tenant,
            state_version_provider=_state_version,
            current_policy_version=APPROVAL_POLICY_VERSION,
            allowed_modes=allowed,
        )
    if _executor is None:
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
@traceable(name="management.detection", run_type="chain", tags=["management"])
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


@router.get("/anomaly/scan")
async def anomaly_scan(
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
    reader=Depends(_request_reader),
):
    """실 캠페인 성과 이상 스캔 — 실제 캠페인을 돌며 성과 진단(ROAS 미달·전환 저조 등)을 모은다.

    데모(/run)는 고장주입이라 실 캠페인엔 못 쓴다. 이건 실 Meta 캠페인의 성과 이상을
    _campaign_diagnosis(실 ROAS·relevance + LLM 재판정)로 실측 진단해 이상 있는 것만 반환.
    use_mock이면 빈 결과(실 스캔은 live 전용).
    """
    if getattr(settings, "use_mock", True):
        return {
            "source": "mock",
            "scanned": 0,
            "anomalies": [],
            "note": "실 캠페인 스캔은 live에서.",
        }
    now = datetime.now(UTC)
    try:
        infos = await reader.list_campaigns()
    except MetaApiError as exc:
        return {
            "source": "live",
            "scanned": 0,
            "anomalies": [],
            "note": exc.user_msg or exc.message,
        }
    anomalies: list[dict] = []
    for c in infos:
        try:
            m = await reader.get_metrics(c.campaign_id, now)
            summary = _real_summary(m, c.daily_budget_krw, conversion_value_krw, target_roas)
            dx = await _campaign_diagnosis(reader, c.campaign_id, summary, m.as_of)
        except Exception:  # noqa: BLE001 — 캠페인 1건 실패가 전체 스캔을 막지 않게
            dx = None
        if dx:  # 진단이 나온(=이상 있는) 캠페인만
            anomalies.append(
                {
                    "campaign_id": c.campaign_id,
                    "name": c.name,
                    "state": c.state.value,
                    "diagnosis": dx,
                }
            )
    return {"source": "live", "scanned": len(infos), "anomalies": anomalies}


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
    # 시연 진단(TENANT_ID 센티넬)은 누구나 자기 계정으로 재생성 허용 — 단 타 실 org 진단은 차단.
    if body.diagnosis.tenant_id not in (str(org_id), TENANT_ID):
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
    em = proposal.evidence_metrics
    # 두 경로 — 수동 create-proposal 형제 키(우선) + from-simulation snapshot 키.
    raw_sim = em.get("simulation_id") or (em.get("simulation_snapshot") or {}).get("simulation_id")
    sim_uuid = None
    if raw_sim:
        try:
            sim_uuid = UUID(str(raw_sim))
        except (ValueError, TypeError):
            sim_uuid = None
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
            creative_ad_id=cfg.get("creative_ad_id"),  # Meta 기존 광고 재사용 귀속
            simulation_id=sim_uuid,  # 시뮬 예측 연결 키(수동 + from-simulation)
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
    # 시연 제안(TENANT_ID 센티넬, 고장주입)은 org 체크 면제 + 항상 DRY_RUN — 데모 캠페인은
    # 실 계정에 없어 실집행이 불가·불필요하다. 실 제안만 org 일치 강제 + 연결 writer로 집행.
    is_demo = body.proposal.tenant_id == TENANT_ID
    if not is_demo:
        if body.proposal.tenant_id != str(org_id):
            raise HTTPException(403, "다른 조직의 제안은 실행할 수 없습니다.")
        if body.approved_action.tenant_id != str(org_id):
            raise HTTPException(403, "다른 조직의 승인은 실행할 수 없습니다.")
    # 시연·mock은 전역 DRY_RUN executor, 실 제안(live)은 로그인 org 연결 writer로 집행.
    executor = (
        _get_executor()
        if is_demo or getattr(settings, "use_mock", True)
        else _get_executor(await _require_writer(db, org_id))
    )
    result = await executor.execute(body.approved_action, body.proposal)
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


def _job_http_error(exc: Exception) -> HTTPException:
    """재생성 job 도메인 예외 → HTTPException. 라우터 분기 단일화."""
    if isinstance(exc, (JobNotFound, JobTenantMismatch)):
        return HTTPException(404, "job을 찾을 수 없습니다.")
    if isinstance(exc, CandidateNotInJob):
        return HTTPException(422, "선택한 후보가 이 job에 없습니다.")
    if isinstance(exc, SelectionContextExpired):
        return HTTPException(409, {"reason": "SELECTION_CONTEXT_EXPIRED"})
    if isinstance(exc, JobNotAwaitingSelection):
        return HTTPException(409, "선택 가능한 상태가 아닙니다.")
    return HTTPException(500, "알 수 없는 오류")


class StartRegenJobRequest(BaseModel):
    diagnosis: DiagnosisResult


class SelectRegenJobRequest(BaseModel):
    selected_id: str


@router.post("/regenerate/jobs")
async def start_regen_job(
    body: StartRegenJobRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """재생성 비동기 job 시작 → {job_id, status}. 무거운 생성은 백그라운드."""
    org_id = await _require_org_id(user, db)
    # 시연 진단(TENANT_ID 센티넬)은 누구나 자기 계정으로 재생성 허용 — 단 타 실 org 진단은 차단.
    if body.diagnosis.tenant_id not in (str(org_id), TENANT_ID):
        raise HTTPException(403, "다른 조직의 진단으로는 재생성할 수 없습니다.")
    ad_account = await _require_ad_account(db, org_id)  # /regenerate와 동일 — live면 fail-closed
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
    service = build_regeneration_job_service(settings)
    job_id = await service.start(body.diagnosis, context)
    return {"job_id": job_id, "status": "queued"}


@router.get("/regenerate/jobs/{job_id}")
async def get_regen_job(
    job_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """재생성 job 진행 상태 조회(폴링) — org 스코프 강제."""
    org_id = await _require_org_id(user, db)
    service = build_regeneration_job_service(settings)
    try:
        rec = await service.get(job_id, tenant_id=str(org_id))
    except (JobNotFound, JobTenantMismatch) as exc:
        raise _job_http_error(exc) from exc
    return {
        "job_id": rec.id,
        "status": rec.status.value,
        "candidates": rec.candidates,
        "proposal": rec.proposal,
        "outcome_reason": rec.outcome_reason,
    }


@router.post("/regenerate/jobs/{job_id}/select")
async def select_regen_job(
    job_id: str,
    body: SelectRegenJobRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _require_org_id(user, db)
    service = build_regeneration_job_service(settings)
    try:
        rec = await service.select(job_id, body.selected_id, tenant_id=str(org_id))
    except (
        JobNotFound,
        JobTenantMismatch,
        JobNotAwaitingSelection,
        CandidateNotInJob,
        SelectionContextExpired,
    ) as exc:
        raise _job_http_error(exc) from exc
    return {"job_id": rec.id, "status": rec.status.value, "proposal": rec.proposal}


@router.get("/execution/history")
async def execution_history_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """테넌트의 최근 실행 감사 이력(읽기) — org 스코프 강제."""
    org_id = await _require_org_id(user, db)
    return await execution_history(_AUDIT_LOG, tenant_id=str(org_id))


# ── 오가닉 vs 광고 비교 (🅰 comparison 도메인 노출) ──────────────────────
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


# 대시보드 조회 기간 토글 — 프론트 전체/최근30일/이번달. Meta date_preset로 매핑. 기본=전체 누적.
_ALLOWED_PRESETS = frozenset({"maximum", "last_30d", "this_month"})


def _valid_preset(preset: str | None) -> str:
    return preset if preset in _ALLOWED_PRESETS else "maximum"


@router.get("/compare")
async def compare_one(post_id: str = "ig_demo_1", campaign_id: str = "camp_demo_1"):
    """단일 오가닉 게시물 ↔ 광고 캠페인 비교 + 🅰 권고 (ComparisonReport).

    제안 생성·집행은 🅱 — 여기는 분석 산출물(상세 리프트 + 권고)만 노출한다.
    비교는 매칭된 오가닉+부스트 쌍이 필요한 데모라 use_mock 무관하게 항상 mock 데이터.
    """
    svc = ComparisonService(MockOrganicReader(), MockAdPlatform())
    report = await svc.compare_and_recommend(post_id, campaign_id, _today_utc())
    return report.model_dump(mode="json")


@router.get("/compare/board")
async def compare_board():
    """여러 게시물의 오가닉→광고 증분 일괄 검증 + 권고 (B 뷰). 매칭 쌍 데모라 항상 mock."""
    organic_reader = MockOrganicReader()  # 데모 게시물 — 실모드에도 mock(실 Meta엔 해당 ID 없음)
    since = _today_utc()
    rows = []
    for title, post_id, campaign_id, budget in _BOARD_DEMO:
        svc = ComparisonService(organic_reader, MockAdPlatform(daily_budget_krw=budget))
        report = await svc.compare_and_recommend(post_id, campaign_id, since)
        rows.append(
            {
                "title": title,
                "lift": report.lift.model_dump(mode="json"),
                "recommendation": report.recommendation.model_dump(mode="json"),
            }
        )
    return {"rows": rows}


async def _campaign_links(
    db: AsyncSession, org_id: UUID | None
) -> tuple[dict[str, str], dict[str, tuple[str, str]]]:
    """created_campaigns에서 meta_id→creative_ad_id, meta_id→(simulation_id, tenant_id) 매핑.

    live(org_id 주어짐)는 tenant=org 행만 로드 — 타 org 행을 meta_id로 잘못 매칭할 여지를 차단.
    mock(org_id=None)은 전체(데모). 매핑 실패는 빈 dict(실측은 그대로 보여줌).
    """
    stmt = select(CreatedCampaign).where(CreatedCampaign.deleted_at.is_(None))
    if org_id is not None:
        stmt = stmt.where(CreatedCampaign.tenant_id == str(org_id))
    creative_by_meta: dict[str, str] = {}
    sim_by_meta: dict[str, tuple[str, str]] = {}
    try:
        for r in (await db.execute(stmt)).scalars().all():
            if not r.meta_campaign_id:
                continue
            if r.creative_ad_id:
                creative_by_meta[str(r.meta_campaign_id)] = r.creative_ad_id
            if r.simulation_id:
                sim_by_meta[str(r.meta_campaign_id)] = (str(r.simulation_id), r.tenant_id)
    except Exception:  # noqa: BLE001 — 매핑 실패해도 실측은 보여준다
        return {}, {}
    return creative_by_meta, sim_by_meta


@router.get("/compare/before-after")
async def compare_before_after(
    reader=Depends(_request_reader),
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """집행 전(시뮬 예측) vs 후(실측) — 실제 Meta 캠페인별(로그인 org 연결 계정).

    후=실 Meta 실측(list_campaigns→get_metrics→RealOutcome). 전=실 시뮬(SimPredictionReader).
    예측·실측 스케일이 달라 환산 없이 나란히 + 정성 판정(compute_before_after).
    예측 링크는 로그인 org의 created_campaigns에서 meta_id로 매핑(없으면 시뮬 미연결).
    """
    pred_reader = build_prediction_reader(settings)
    now = datetime.now(UTC)
    org_id = (
        await _require_org_id(user, db)
        if user is not None and not getattr(settings, "use_mock", True)
        else None
    )
    creative_by_meta, sim_by_meta = await _campaign_links(db, org_id)
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

    async def _row(c) -> dict | None:
        cid = c.campaign_id
        m, _blocked = await _safe_meta(reader.get_metrics(cid, now))
        if m is None:  # 캠페인 1건 실측 실패/권한거부는 건너뜀(전체를 막지 않게)
            return None
        link = sim_by_meta.get(cid)
        prediction = await pred_reader.get_prediction(link[0], link[1]) if link else None
        actual = _real_outcome(m, cid, creative_by_meta.get(cid))
        return compute_before_after(cid, c.name, prediction, actual).model_dump(mode="json")

    # 캠페인 단위 병렬 — 순차 N회 Meta 왕복이 직렬로 쌓이지 않게(_list_campaigns_real과 동일).
    rows = await asyncio.gather(*(_row(c) for c in campaigns))
    items = [r for r in rows if r is not None]
    return {"items": items}


@router.get("/campaigns/{campaign_id}/targeting")
async def get_campaign_targeting(
    campaign_id: str,
    reader=Depends(_request_reader),
):
    """Meta 캠페인 타겟팅 정보 — 시뮬레이터 사전 입력용.

    objective·age_min·age_max·gender를 반환한다. 시뮬레이터 입력 폼에 그대로 매핑된다.
    """
    return await reader.get_campaign_targeting(campaign_id)


class _LinkSimBody(BaseModel):
    simulation_id: str


@router.post("/campaigns/{campaign_id}/link-simulation")
async def link_simulation(
    campaign_id: str,
    body: _LinkSimBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """기존 Meta 캠페인에 시뮬 결과를 역방향 연결 — management_created_campaigns에 기록.

    ClickMe 밖에서 만든 캠페인도 시뮬 예측과 성과 비교가 가능해진다.
    이미 연결된 캠페인은 simulation_id를 덮어쓴다(재시뮬 시).
    """
    org_id = await _require_org_id(user, db)
    try:
        sim_uuid = UUID(body.simulation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="simulation_id 형식 오류") from exc
    owned = await db.scalar(
        text("SELECT 1 FROM simulations WHERE id = :sid AND organization_id = :org"),
        {"sid": str(sim_uuid), "org": str(org_id)},
    )
    if not owned:
        raise HTTPException(status_code=422, detail="해당 시뮬을 찾을 수 없거나 권한이 없습니다.")
    existing = await db.scalar(
        select(CreatedCampaign).where(
            CreatedCampaign.meta_campaign_id == campaign_id,
            CreatedCampaign.tenant_id == str(org_id),
            CreatedCampaign.deleted_at.is_(None),
        )
    )
    if existing:
        existing.simulation_id = str(sim_uuid)
    else:
        conn = await db.scalar(
            select(MetaConnection).where(
                MetaConnection.organization_id == str(org_id),
                MetaConnection.deleted_at.is_(None),
            )
        )
        ad_account_id = conn.ad_account_id if conn else ""
        db.add(
            CreatedCampaign(
                tenant_id=str(org_id),
                meta_campaign_id=campaign_id,
                simulation_id=str(sim_uuid),
                name=campaign_id,
                objective="unknown",
                ad_account_id=ad_account_id,
                daily_budget_krw=0,
                status="linked",
                execution_mode="manual_link",
            )
        )
    await db.commit()
    return {"campaign_id": campaign_id, "simulation_id": str(sim_uuid), "linked": True}


@router.get("/campaigns/{campaign_id}/creative-image")
async def proxy_creative_image(
    campaign_id: str,
    reader=Depends(_request_reader),
):
    """Meta 크리에이티브 이미지 프록시 — 브라우저에서 직접 접근 불가한 fbcdn URL을 서버가 중계.

    Meta CDN(fbcdn.net)은 CORS 제한과 세션 만료로 브라우저 직접 로드가 막힌다.
    백엔드가 이미지를 받아 Content-Type 그대로 스트림으로 반환한다.
    """
    creatives = await reader.get_creatives(campaign_id)
    image_url: str | None = None
    for c in creatives:
        if c.image_url:
            image_url = c.image_url
            break
    if not image_url:
        raise HTTPException(
            status_code=404, detail="이미지 없음 — 크리에이티브에 이미지가 설정되지 않았습니다."
        )
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(image_url)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Meta 이미지 조회 실패")
        content_type = resp.headers.get("content-type", "image/jpeg")
        return StreamingResponse(
            iter([resp.content]),
            media_type=content_type,
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Meta 이미지 네트워크 오류") from exc


@router.get("/calibration/anchors")
async def calibration_anchors(
    reader=Depends(_request_reader),
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """베이스라인 앵커 자동 수집 — 연결된(시뮬↔캠페인) 광고의 예측↔실측 쌍 + 방향성 정합.

    compare와 동일 연결 키(로그인 org created_campaigns.simulation_id → SimPredictionReader).
    노출 0·미연결은 제외(판정 불가). 절대 환산 없이 순위 일치율(concordance)만 계산.
    별도 영속 없이 매번 모으므로, 연결 캠페인이 늘면 앵커도 자동 누적된다.
    """
    pred_reader = build_prediction_reader(settings)
    now = datetime.now(UTC)
    org_id = (
        await _require_org_id(user, db)
        if user is not None and not getattr(settings, "use_mock", True)
        else None
    )
    _, sim_by_meta = await _campaign_links(db, org_id)

    empty = {"anchors": [], "summary": build_summary([]).model_dump(mode="json")}
    try:
        campaigns = await reader.list_campaigns()
    except MetaApiError as exc:
        if exc.is_rate_limited:
            return {**empty, "rate_limited": "Meta 요청 한도 — 잠시 후 다시 시도하세요."}
        return empty
    except Exception:  # noqa: BLE001
        return empty

    async def _anchor(c) -> CalibrationAnchor | None:
        link = sim_by_meta.get(c.campaign_id)
        if not link:
            return None
        prediction = await pred_reader.get_prediction(link[0], link[1])
        if prediction is None:
            return None
        m, _blocked = await _safe_meta(reader.get_metrics(c.campaign_id, now))
        if m is None or m.impressions == 0:  # 실측 실패·권한거부·노출 0은 판정 불가 — 제외
            return None
        return CalibrationAnchor(
            campaign_id=c.campaign_id,
            name=c.name,
            source=prediction.source,
            predicted_click_intent=prediction.click_intent_rate,
            actual_ctr=m.ctr,
            predicted_purchase_intent=prediction.purchase_intent,
            actual_cvr=m.cvr,
            predicted_rejection=prediction.rejection_rate,
            actual_impressions=m.impressions,
            actual_spend_krw=m.spend_krw,
        )

    # 캠페인 단위 병렬 — 순차 Meta 왕복 누적 방지.
    collected = [a for a in await asyncio.gather(*(_anchor(c) for c in campaigns)) if a is not None]
    summary = build_summary(collected)
    return {
        "anchors": [a.model_dump(mode="json") for a in collected],
        "summary": summary.model_dump(mode="json"),
    }


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


@router.post("/kb/refresh")
async def kb_refresh() -> dict:
    """KB 증분 재적재 — 변경된 문서만 재임베딩(content_hash diff). 운영자 트리거.

    자동 스케줄러·외부 소스(웹) 수집은 후속(소스·파서·스케줄러 결정 필요). 현재는 로컬 KB
    문서를 재적재하며, 증분이라 변경 없으면 비용 없이 즉시 반환한다.
    """
    from domain.management.assistant.kb_ingest import ingest  # noqa: PLC0415

    ingested = await ingest()
    return {"ok": True, "ingested_chunks": ingested}


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
        # mock은 하루치 합성이라 7일 빈도 개념이 없음 — 당일 빈도를 그대로 노출 피로 입력으로.
        "frequency_7d": last.frequency,
        # mock은 하루치(시간행) 합성이라 총 지출이 곧 오늘 지출 — 소진율 분자로 그대로 쓴다.
        "spend_today_krw": total_spend,
        "pacing_pct": round(total_spend / budget * 100, 1) if budget else 0.0,
    }


def _real_summary(
    m: MetricsSnapshot,
    budget: int,
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
    spend_today_krw: int = 0,
    frequency_7d: float = 0.0,
) -> dict:
    """실 reader 단일 집계 스냅샷 → 대시보드 요약.

    전환 필드가 응답에 있으면 CVR·ROAS까지 실측으로 표시하고, 없으면 합성하지 않는다.
    매출이 측정 안 되는(구매 외) 전환은 ROAS가 None인데, 고객이 전환 가치를 입력하면
    그 통계가치로 ROAS를 추정해 채운다(roas_estimated=True로 '추정' 표기 책임을 넘김).
    target_roas(고객 목표) 입력 시 실제 ROAS가 목표 대비 미달이면 target_missed=True.
    소진율(pacing)은 '오늘' 지출÷일예산 — 일예산은 하루 단위라 조회기간 누적(spend_krw)이
    아니라 spend_today_krw로 계산한다(조회기간 토글과 무관).
    노출 피로는 최근 7일 빈도(frequency_7d) — frequency(조회기간 윈도)와 분리해 고정 윈도로 판정.
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
        # frequency_7d=최근 7일 빈도(노출 피로용), frequency=조회기간 윈도 빈도(표시용).
        "frequency_7d": frequency_7d,
        # spend_today_krw=오늘 지출(소진율용), spend_krw=조회기간 누적(총 지출용)으로 분리.
        "spend_today_krw": spend_today_krw,
        "pacing_pct": round(spend_today_krw / budget * 100, 1) if budget else 0.0,
    }


async def _safe_meta(coro: Awaitable[Any]) -> tuple[Any, bool]:
    """Meta 호출을 권한 거부에 안전하게 감싼다 — 권한 에러면 (None, True), 성공이면 (result, False).

    인증·레이트리밋·기타 에러는 상위 핸들러가 처리하도록 그대로 전파한다.
    """
    try:
        return await coro, False
    except MetaApiError as exc:
        if exc.is_permission_error:
            return None, True
        raise


def _blocked_summary() -> dict:
    """권한 거부로 지표를 못 읽은 캠페인의 요약 자리표시 — metrics_status로 '권한 없음' 표기용."""
    return {
        "impressions": 0,
        "clicks": 0,
        "reach": 0,
        "spend_krw": 0,
        "ctr": 0.0,
        "cpc_krw": 0,
        "cpm_krw": 0,
        "conversions": None,
        "cvr": None,
        "roas": None,
        "roas_estimated": False,
        "target_roas": None,
        "target_missed": False,
        "conversion_tracking": False,
        "frequency": 0.0,
        "frequency_7d": 0.0,
        "spend_today_krw": 0,
        "pacing_pct": 0.0,
    }


async def _reconcile_deleted_campaigns(
    db: AsyncSession, org_id: UUID | None, live_campaign_ids: set[str]
) -> None:
    """Meta에 없는(외부 삭제된) 적재 캠페인을 소프트삭제로 동기화 — 양방향 삭제(Meta→앱·DB).

    Meta Ads Manager에서 직접 삭제하면 앱 미경유라 DB 기록이 '활성'으로 남는다. 목록을
    성공적으로 받아온 시점에, 이 계정의 활성 기록 중 Meta 목록에 없는 것을 deleted_at 처리.
    org_id로 로그인 org 연결 계정만 스코프(전역 lookup 금지 — 타 org 캠페인 오삭제 방지).
    live_campaign_ids는 '보관 포함' 전체 id여야 한다 — 보관(미삭제)을 외부삭제로 오인하지 않게.
    """
    if org_id is None:
        return  # org 불명이면 미수행(크로스테넌트 오삭제 방지)
    conn = await db.scalar(select(MetaConnection).where(MetaConnection.organization_id == org_id))
    if conn is None or not conn.ad_account_id:
        return
    rows = (
        (
            await db.execute(
                select(CreatedCampaign).where(
                    CreatedCampaign.tenant_id == str(org_id),
                    CreatedCampaign.ad_account_id == conn.ad_account_id,
                    CreatedCampaign.meta_campaign_id.is_not(None),
                    CreatedCampaign.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    changed = False
    for r in rows:
        if r.meta_campaign_id not in live_campaign_ids:
            r.deleted_at = func.now()
            changed = True
    if changed:
        await db.commit()


async def _list_campaigns_real(
    reader,
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
    date_preset: str = "maximum",
    db: AsyncSession | None = None,
    include_archived: bool = False,
    org_id: UUID | None = None,
) -> dict:
    """실연동 — Meta 캠페인 목록 + 캠페인별 실측 요약. date_preset=조회 기간(전체/30일/이번달).

    reader는 호출자(로그인 org 연결)가 주입 — 멀티테넌시 정합(전역 settings 계정 금지).
    include_archived=True면 보관/삭제 캠페인도 '삭제됨'으로 포함(과거 데이터 조회용).
    계정 자금·캠페인별 지표는 권한 거부에 안전하게 감싸, 한 부분의 권한이 없어도 화면을
    깨지 않고 그 부분만 '권한 없음'(account_unavailable·metrics_status)으로 표기한다.
    db가 주어지면 외부(Meta) 삭제분을 DB에 소프트삭제로 동기화한다(양방향 삭제).
    """
    since = _today_utc()
    # 목록·계정 자금 병렬. 자금은 권한 거부가 잦아 _safe_meta로 격리(목록 권한 에러는 상위로 전파).
    infos, (funding, funding_blocked) = await asyncio.gather(
        reader.list_campaigns(include_archived),
        _safe_meta(reader.get_account_funding()),
    )
    # 외부(Meta) 삭제분 → DB 소프트삭제 동기화(양방향 삭제, 로그인 org만).
    # 비교 id는 '보관 포함' 전체로 — 보관(미삭제)을 외부삭제로 오인해 링크가 끊기지 않게.
    if db is not None and org_id is not None:
        recon_ids = (
            {info.campaign_id for info in infos}
            if include_archived
            else {c.campaign_id for c in await reader.list_campaigns(include_archived=True)}
        )
        await _reconcile_deleted_campaigns(db, org_id, recon_ids)
    # 캠페인별 조회기간 지표 — 계정 단위 level=campaign 1콜(+페이징)로 N+1 제거.
    # 권한 거부는 배치 전체가 막힘(계정 insights 권한은 균일) → 전 캠페인 (None, True).
    ids = [c.campaign_id for c in infos]
    metrics_map, metrics_blocked = await _safe_meta(
        reader.get_metrics_by_campaign(ids, since, date_preset=date_preset)
    )
    metrics_map = metrics_map or {}
    metric_pairs = [(metrics_map.get(cid), metrics_blocked) for cid in ids]
    # 운영 신호는 조회기간과 분리한 고정 윈도로 — 소진율=오늘 지출÷일예산, 노출 피로=최근 7일 빈도.
    # 지표를 읽은 active만 today·last_7d 추가 조회(권한 거부·비활성은 건너뜀).
    today_spend = [0] * len(infos)
    freq_7d = [0.0] * len(infos)
    elig = [
        i for i, c in enumerate(infos) if c.state == CampaignState.ACTIVE and not metric_pairs[i][1]
    ]
    if elig:
        elig_ids = [infos[i].campaign_id for i in elig]
        (today_map, _t_blocked), (week_map, _w_blocked) = await asyncio.gather(
            _safe_meta(reader.get_metrics_by_campaign(elig_ids, since, date_preset="today")),
            _safe_meta(reader.get_metrics_by_campaign(elig_ids, since, date_preset="last_7d")),
        )
        today_map = today_map or {}
        week_map = week_map or {}
        for i in elig:
            cid = infos[i].campaign_id
            tm = today_map.get(cid)
            wm = week_map.get(cid)
            if tm is not None:
                today_spend[i] = tm.spend_krw
            if wm is not None:
                freq_7d[i] = wm.frequency
    out = []
    any_blocked = False
    for idx, info in enumerate(infos):
        m, m_blocked = metric_pairs[idx]
        # 게재 차단: 계정 자금 막힘 + 캠페인이 켜져 있는데(ACTIVE) 안 도는 경우.
        blocked = (
            funding is not None and funding.delivery_blocked and info.state == CampaignState.ACTIVE
        )
        any_blocked = any_blocked or blocked
        if m_blocked or m is None:
            summary, metrics_status = _blocked_summary(), "permission"
        else:
            summary = _real_summary(
                m,
                info.daily_budget_krw,
                conversion_value_krw,
                target_roas,
                spend_today_krw=today_spend[idx],
                frequency_7d=freq_7d[idx],
            )
            metrics_status = "ok"
        out.append(
            {
                "campaign_id": info.campaign_id,
                "name": info.name,
                "state": info.state.value,
                "daily_budget_krw": info.daily_budget_krw,
                "lifetime_budget_krw": info.lifetime_budget_krw,
                "budget_type": info.budget_type,
                "ended_at": info.ended_at,
                "delivery_blocked": blocked,
                "block_reason": funding.block_reason if (blocked and funding) else None,
                "metrics_status": metrics_status,
                **summary,
            }
        )
    if funding_blocked or funding is None:
        # 계정 자금 권한 없음 — 지갑은 '권한 없음'으로, 게재중단 배너는 판단 불가라 숨김.
        account = None
        account_unavailable = "권한 없음 — 계정 자금(잔액·한도·누적지출) 조회 권한이 없어요."
    else:
        # 계정 지갑(돈 개념 분리) — 일일예산과 다른 '실제 충전·지출·잔액'
        account = {
            "available_balance_krw": funding.available_balance_krw,
            "spend_cap_krw": funding.spend_cap_krw,
            "amount_spent_krw": funding.amount_spent_krw,
        }
        account_unavailable = None
    return {
        "campaigns": out,
        "source": "live",
        # 계정 배너는 실제로 막힌(진행중) 캠페인이 있을 때만 — 전부 종료면 노이즈라 숨김
        "account_block_reason": funding.block_reason if (funding and any_blocked) else None,
        "account": account,
        "account_unavailable": account_unavailable,
    }


@traceable(name="management.performance_diagnosis", run_type="chain", tags=["management"])
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
    reader,
    campaign_id: str,
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
    date_preset: str = "maximum",
) -> dict:
    """실연동 — 캠페인 상세(시간별 실측 + 기대곡선 + 요약 + 성과 미달 진단).

    reader는 호출자(로그인 org 연결)가 주입 — 멀티테넌시 정합. 예산(일/총)·상태는 목록에서,
    지표 묶음은 권한 거부에 안전하게 감싸 분리한다 — 지표 권한이 없으면 상세 수치만
    '권한 없음'으로 비우고 화면은 유지(budget·이름은 표시).
    """
    today = _today_utc()
    # 보관/삭제 캠페인 상세도 열 수 있게 archived 포함 조회(상세는 by-id라 데이터는 그대로 조회됨).
    campaigns = await reader.list_campaigns(include_archived=True)
    info = next((c for c in campaigns if c.campaign_id == campaign_id), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"캠페인 없음: {campaign_id}")
    budget_fields = {
        "daily_budget_krw": info.daily_budget_krw,
        "lifetime_budget_krw": info.lifetime_budget_krw,
        "budget_type": info.budget_type,
    }
    # 시간별·일별·요약·7일 묶음 병렬 — 권한 거부면 상세 지표만 비우고 화면은 유지.
    bundle, blocked = await _safe_meta(
        asyncio.gather(
            reader.fetch_hourly_metrics(campaign_id, today),
            reader.get_metrics(campaign_id, today, date_preset=date_preset),
            reader.fetch_daily_metrics(campaign_id),
            reader.get_metrics(campaign_id, today, date_preset="last_7d"),  # 노출 피로용 7일 빈도
        )
    )
    if blocked or bundle is None:
        return {
            "campaign_id": info.campaign_id,
            "name": info.name,
            "state": info.state.value,
            **budget_fields,
            "expected": [],
            "actual": [],
            "anomaly_hours": [],
            "series": [],
            "summary": _blocked_summary(),
            "metrics_status": "permission",
            "diagnosis": None,
        }
    snaps, m, daily, week = bundle
    actual = [s.impressions for s in snaps]
    expected = expected_hourly_impressions(info.daily_budget_krw)
    # 소진율은 오늘 지출 기준 — 이미 받은 시간행(snaps) 합으로 추가 호출 없이 산출.
    spend_today = sum(s.spend_krw for s in snaps)
    summary = _real_summary(
        m,
        info.daily_budget_krw,
        conversion_value_krw,
        target_roas,
        spend_today_krw=spend_today,
        frequency_7d=week.frequency,
    )
    return {
        "campaign_id": info.campaign_id,
        "name": info.name,
        "state": info.state.value,
        **budget_fields,
        "expected": [round(e, 1) for e in expected],
        "actual": actual,
        "anomaly_hours": find_anomaly_window(expected, actual) if actual else [],
        "series": daily,
        "summary": summary,
        "metrics_status": "ok",
        "diagnosis": await _campaign_diagnosis(reader, campaign_id, summary, m.as_of),
    }


@router.get("/campaigns")
async def list_campaigns(
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
    date_preset: str = "maximum",
    include_archived: bool = False,
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 목록 + 캠페인별 성과 요약 (단일 창구 대시보드).

    live는 로그인 org의 Meta 연결 계정만 보여준다(멀티테넌시 정합 — 전역 settings 계정 금지).
    비로그인·미연결 org는 빈 목록 + 안내(남의 계정 노출 금지). mock은 무인증 데모 유지.
    include_archived=True면 보관/삭제 캠페인도 '삭제됨'으로 포함(과거 데이터 조회용).
    목록 조회 시 외부(Meta) 삭제분을 DB에 소프트삭제로 동기화한다(양방향 삭제).
    """
    if not getattr(settings, "use_mock", True):
        if user is None:
            return {"campaigns": [], "source": "live", "auth_error": "로그인이 필요합니다."}
        org_id = await _require_org_id(user, db)
        reader = await _resolve_reader(db, org_id)
        if reader is None:
            return {"campaigns": [], "source": "live", "not_connected": _NOT_CONNECTED_MSG}
        try:
            return await _list_campaigns_real(
                reader,
                conversion_value_krw,
                target_roas,
                _valid_preset(date_preset),
                db,
                include_archived,
                org_id=org_id,
            )
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
            # 목록 자체를 권한 거부당한 경우 — 빈 목록 + '권한 없음' 안내(화면 깨지 않음).
            if exc.is_permission_error:
                return {
                    "campaigns": [],
                    "source": "live",
                    "account": None,
                    "account_unavailable": "권한 없음 — 계정 자금 조회 권한이 없어요.",
                    "permission_error": (
                        "권한 없음 — Meta 광고 데이터 접근 권한이 없어요. "
                        "토큰 권한(스코프)·자산(광고계정) 권한을 확인해 주세요."
                    ),
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
                "lifetime_budget_krw": 0,
                "budget_type": "daily",  # 데모는 모두 일예산
                "metrics_status": "ok",
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
async def get_campaign_outcome(
    campaign_id: str, creative_id: str | None = None, reader=Depends(_request_reader)
):
    """집행 후 실측 성과(RealOutcome) — 시뮬 예측 vs 실측 캘리브레이션 소비용 seam.

    wiring 경유라 use_mock=False면 Meta 실측, True면 데모. creative_id는 집행한 크리에이티브
    귀속(생성→집행 경로가 stamp; 없으면 None).
    """
    m = await reader.get_metrics(campaign_id, _today_utc())
    return _real_outcome(m, campaign_id, creative_id).model_dump(mode="json")


@router.get("/campaigns/{campaign_id}/platforms")
async def get_campaign_platforms(campaign_id: str, reader=Depends(_request_reader)):
    """게재 플랫폼별(FB/IG 등) 노출·클릭·지출·도달 분해 (publisher_platform)."""
    rows = await reader.get_platform_breakdown(campaign_id, _today_utc())
    return {"platforms": [r.model_dump(mode="json") for r in rows]}


@router.get("/campaigns/{campaign_id}/demographics")
async def get_campaign_demographics(campaign_id: str, reader=Depends(_request_reader)):
    """연령×성별(age,gender) 노출·클릭·지출·도달 분해."""
    rows = await reader.get_demographic_breakdown(campaign_id, _today_utc())
    return {"demographics": [r.model_dump(mode="json") for r in rows]}


@router.get("/campaigns/{campaign_id}/creatives")
async def get_campaign_creatives(campaign_id: str, reader=Depends(_request_reader)):
    """캠페인 대표 크리에이티브 — 광고 시안 이름·썸네일."""
    rows = await reader.get_creatives(campaign_id)
    return {"creatives": [r.model_dump(mode="json") for r in rows]}


# ── 수동 KPI(추정 CVR·ROAS) — 조직 단위 DB 영속 (전환 추적 전 고객 입력값) ──


class KpiOverrideBody(BaseModel):
    cvr: float | None = None  # 전환율 % (수동 추정)
    roas: float | None = None  # 투자수익률 배수 (수동 추정)


_resolve_org_id = user_org_id  # core.auth 공용(없으면 None) — 라우터 복붙 제거


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
async def delete_campaign(
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 삭제 — 자식 광고세트·광고도 함께. LIVE 모드에서만 실제 Meta 삭제(그 외 무동작).

    적재 기록(created_campaigns)은 지우지 않고 deleted_at만 찍는다(감사 이력 — 만듦→지움 보존).
    """
    org_id = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_id, campaign_id)
    writer = await _require_writer(db, org_id)
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
    campaign_id: str,
    conversion_value_krw: int | None = None,
    target_roas: float | None = None,
    date_preset: str = "maximum",
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 상세 — 시간별 노출(기대 vs 실측, 이상구간) + 요약 KPI. date_preset=조회 기간.

    live는 로그인 org 연결 계정 기준(멀티테넌시 정합) — 미연결이면 409.
    """
    if not getattr(settings, "use_mock", True):
        if user is None:
            raise HTTPException(401, "인증 토큰이 없습니다.")
        reader = await _require_reader(db, await _require_org_id(user, db))
        return await _get_campaign_real(
            reader, campaign_id, conversion_value_krw, target_roas, _valid_preset(date_preset)
        )
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
                "lifetime_budget_krw": 0,
                "budget_type": "daily",
                "expected": [round(e, 1) for e in expected],
                "actual": actual,
                "anomaly_hours": find_anomaly_window(expected, actual),
                "series": await MockAdPlatform().fetch_daily_metrics(cid),
                "summary": _campaign_summary(snaps, budget),
                "metrics_status": "ok",
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


async def _upload_creative_or_502(
    writer, config: CampaignConfig, image_bytes: bytes, filename: str
) -> str | None:
    """소재 이미지를 Meta(/adimages)에 업로드 — 실패는 사유와 함께 502로 변환.

    /adimages는 validate_only가 안 먹는 실호출이라, 앱 권한 부족(#3) 등 MetaApiError가 raw 500으로
    새지 않게 user_msg를 담아 502로 정리한다. dry_run/mock은 writer가 None을 반환(미전송, 정상).
    """
    try:
        return await writer.upload_image(
            config, image_bytes, filename, idem_key=f"img_{uuid4().hex[:8]}"
        )
    except MetaApiError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Meta 이미지 업로드 실패: {exc.user_msg or exc.message}",
        ) from exc


class CreateCampaignRequest(BaseModel):
    name: str
    objective: Literal["traffic", "leads"] = "traffic"  # 트래픽(클릭) / 리드(잠재고객)
    daily_budget_krw: int = Field(ge=1)  # 실제 최소는 핸들러가 라이브 정책(Meta floor)으로 검증
    run_days: int = Field(ge=1, le=90)
    simulation_id: str | None = None  # 이 캠페인이 연결될 시뮬 런(UUID). 없으면 예측 미연결.
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
async def campaign_policy(reader=Depends(_request_reader)):
    """캠페인 생성 정책 — 최소 일예산(Meta 실시간)·특별광고카테고리·연령. 폼이 동적 검증에 사용."""
    return await get_campaign_policy(reader)


# 미리보기 포맷 — 페이스북 피드 + 인스타그램(자동 배치라 둘 다 노출됨).
_PREVIEW_FORMATS = ["MOBILE_FEED_STANDARD", "INSTAGRAM_STANDARD"]


@router.post("/ad-image")
async def upload_ad_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """광고 소재 이미지를 Meta(/adimages)에 업로드 → image_hash 반환. 무과금(자산 등록)."""
    writer = await _require_writer(db, await _require_org_id(user, db))
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
async def ad_preview(body: AdPreviewRequest, writer=Depends(_request_writer)):
    """샘플 시안 — 업로드 이미지로 FB 피드·인스타 미리보기(Meta 호스팅 iframe). 무과금(읽기)."""
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
    policy = await get_campaign_policy(await _require_reader(db, org_id))
    min_budget = min_daily_budget_for(body.objective, policy)
    if body.daily_budget_krw < min_budget:
        raise HTTPException(
            status_code=422,
            detail=f"{body.objective} 캠페인의 최소 일예산은 ₩{min_budget:,}입니다 (Meta 정책).",
        )
    # 시뮬 연결 키 — 형식·org 소유 검증(방어 심층, 읽기 시점 대조와 이중).
    if body.simulation_id is not None:
        try:
            sid = UUID(body.simulation_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="simulation_id 형식 오류") from exc
        owned = await db.scalar(
            text("SELECT 1 FROM simulations WHERE id = :sid AND organization_id = :org"),
            {"sid": str(sid), "org": str(org_id)},
        )
        if not owned:
            raise HTTPException(
                status_code=422, detail="해당 시뮬을 찾을 수 없거나 권한이 없습니다."
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
                "simulation_id": body.simulation_id,
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
    # writer _OBJECTIVE_MAP이 구현한 목적만 수신 — 그 외(인지도·판매 등)는 미지원(추후 해금).
    objective: Literal["traffic", "leads"] = "traffic"
    link_url: HttpUrl | None = None
    name: str
    daily_budget_krw: int = Field(ge=1)
    # Meta 광고세트 start_time/end_time에 대응 — YYYY-MM-DD. 종료일 없으면 시작+7일.
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
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

    org_id = await _require_org_id(user, db)
    writer = await _require_writer(db, org_id)
    image_hash = await _upload_creative_or_502(
        writer, _asset_config(name=body.name), image_bytes, "candidate.png"
    )
    if _is_sending_mode() and not image_hash:
        raise HTTPException(status_code=502, detail="Meta 이미지 업로드 실패.")

    policy = await get_campaign_policy(await _require_reader(db, org_id))
    min_budget = min_daily_budget_for(body.objective, policy)
    if body.daily_budget_krw < min_budget:
        raise HTTPException(status_code=422, detail=f"최소 일예산은 ₩{min_budget:,}입니다.")

    now = datetime.now(UTC)
    ad_account = await _require_ad_account(db, org_id)
    tenant_id = str(org_id)
    genders = {"all": (), "male": (1,), "female": (2,)}[body.gender]
    categories = () if body.special_ad_category == "NONE" else (body.special_ad_category,)
    # Meta start_time/end_time 매핑 — 시작이 과거면 now로 끌어올림(writer가 추가로 24h 보정).
    start_at = datetime.strptime(body.start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    if start_at < now:
        start_at = now
    end_at = (
        datetime.strptime(body.end_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if body.end_date
        else start_at + timedelta(days=7)
    )
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="종료일은 시작일 이후여야 합니다.")
    run_days = max(1, (end_at - start_at).days)  # spend_cap 산정용(일예산 × 일수)
    config = CampaignConfig(
        campaign_id=f"camp_cand_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ad_account_id=ad_account,
        name=body.name,
        objective=body.objective,
        daily_budget_krw=body.daily_budget_krw,
        start_at=start_at,
        end_at=end_at,
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
            max_total_spend_krw=body.daily_budget_krw * run_days,
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )
    return {"proposal": proposal.model_dump(mode="json")}


# 우리 S3 영속 네임스페이스 — 이 prefix 키만 핸드오프 집행 허용(임시·외부는 차단).
# generated-ads/ = 제너레이터 실제 저장 접두사(tools/storage/s3.py candidate_key). 누락 시
# 제너레이터 광고도 "durable 아님"으로 집행이 막혀, 양식을 맞춰 포함한다.
_DURABLE_KEY_PREFIXES = ("generator/", "ads/", "generated-ads/")


def _resolve_sim_asset_key(asset_url: str | None) -> str | None:
    """시뮬 asset_url에서 우리 S3 키만 추출 — generator 이미지 URL(?key=) 또는 우리 버킷 prefix 키.
    임시 로컬 파일·외부 URL은 None(호출부 422). 임의 URL fetch 금지(SSRF 차단)."""
    if not asset_url:
        return None
    parsed = urlparse(asset_url)
    keys = parse_qs(parsed.query).get("key")
    if keys:
        key = keys[0]
        return key if key.startswith(_DURABLE_KEY_PREFIXES) else None
    if not parsed.scheme and asset_url.startswith(_DURABLE_KEY_PREFIXES):
        return asset_url
    # 우리 S3 버킷 URL(presigned 포함)이면 경로에서 키 추출 — 서명 쿼리는 무시, 객체는 키로 재취득.
    host = parsed.netloc.lower()
    bucket = (settings.s3_bucket_name or "").lower()
    if bucket and host.endswith("amazonaws.com"):
        path_key = parsed.path.lstrip("/")
        if path_key.startswith(bucket + "/"):  # path-style: /bucket/key
            path_key = path_key[len(bucket) + 1 :]
        elif bucket not in host:  # virtual-hosted는 host에 버킷명이 있어야 함
            path_key = ""
        if path_key.startswith(_DURABLE_KEY_PREFIXES):
            return path_key
    return None


def _is_executable_verdict(click_intent_rate: float, rejection_rate: float) -> bool:
    """'집행 권장' 게이트 — 집행 가능 여부 판정(백엔드 정본).

    ⚠️ 임시(TEST): 게이트 해제 — 모든 시뮬 결과 통과(클릭≥0·거부≤100%).
    운영 복원: ``return click_intent_rate >= 0.2 and rejection_rate < 0.2``.
    프론트 EXEC_CIR/EXEC_REJ(ExecuteFromSimulation.tsx)도 함께 0/1 → 0.2/0.2로 되돌릴 것.
    """
    return click_intent_rate >= 0.0 and rejection_rate <= 1.0


class FromSimulationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulation_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    link_url: HttpUrl | None = None
    name: str
    daily_budget_krw: int = Field(ge=1)
    # Meta 광고세트 start_time/end_time에 대응 — YYYY-MM-DD. 종료일 없으면 시작+7일.
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    special_ad_category: Literal[
        "NONE", "HOUSING", "EMPLOYMENT", "CREDIT", "ISSUES_ELECTIONS_POLITICS"
    ] = "NONE"
    country: str = "KR"
    age_min: int = Field(default=18, ge=18, le=65)
    age_max: int = Field(default=65, ge=18, le=65)
    gender: Literal["all", "male", "female"] = "all"


@router.post("/campaign-proposals/from-simulation")
async def from_simulation(
    body: FromSimulationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """시뮬(generator-소스) → CREATE_CAMPAIGN(traffic) 제안. 승인·집행은 /approve·/execute 재사용.

    Simulation/SimulationAggregate는 domain.simulation 내부 모델이라 import 금지 — raw SQL로만 읽음
    (임시 결합, 추후 시뮬 read 계약으로 교체).
    """
    try:
        sim_uuid = UUID(body.simulation_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="잘못된 simulation_id") from exc

    org_id = await _require_org_id(user, db)

    sim_row = (
        await db.execute(
            text("SELECT organization_id, ad_id FROM simulations WHERE id = :sid"),
            {"sid": sim_uuid},
        )
    ).first()
    if sim_row is None or sim_row[0] != org_id:
        raise HTTPException(status_code=404, detail="시뮬레이션을 찾을 수 없습니다.")
    ad_id = sim_row[1]

    agg_row = (
        await db.execute(
            text(
                "SELECT click_intent_rate, rejection_rate FROM simulation_aggregates "
                "WHERE simulation_id = :sid"
            ),
            {"sid": sim_uuid},
        )
    ).first()
    if agg_row is None:
        raise HTTPException(status_code=409, detail="시뮬 집계가 없습니다(미완료).")
    cir, rej = float(agg_row[0]), float(agg_row[1])
    if not _is_executable_verdict(cir, rej):
        raise HTTPException(status_code=409, detail="집행 권장 결과가 아닙니다.")

    ad_row = (
        await db.execute(
            text("SELECT title, asset_url, copy_text FROM ads WHERE id = :aid"),
            {"aid": ad_id},
        )
    ).first()
    if ad_row is None:
        raise HTTPException(status_code=404, detail="광고를 찾을 수 없습니다.")
    title, asset_url, copy_text = ad_row[0], ad_row[1], ad_row[2]

    s3_key = _resolve_sim_asset_key(asset_url)
    if not s3_key:
        raise HTTPException(
            status_code=422, detail="durable S3 이미지가 아닙니다(업로드 광고 집행은 추후)."
        )

    link_url = _resolve_link_url(body.link_url)
    if not link_url:
        raise HTTPException(status_code=422, detail="목적지 URL(link_url)이 필요합니다.")

    try:
        image_bytes = await download_bytes(s3_key)
    except Exception as exc:  # noqa: BLE001 — S3 유실/손상은 입력 문제로 거부
        raise HTTPException(status_code=422, detail="시뮬 이미지를 읽을 수 없습니다.") from exc

    writer = await _require_writer(db, org_id)
    image_hash = await _upload_creative_or_502(
        writer, _asset_config(name=body.name), image_bytes, "creative.png"
    )
    if _is_sending_mode() and not image_hash:
        raise HTTPException(status_code=502, detail="Meta 이미지 업로드 실패.")

    policy = await get_campaign_policy(await _require_reader(db, org_id))
    min_budget = min_daily_budget_for("traffic", policy)
    if body.daily_budget_krw < min_budget:
        raise HTTPException(status_code=422, detail=f"최소 일예산은 ₩{min_budget:,}입니다.")

    now = datetime.now(UTC)
    ad_account = await _require_ad_account(db, org_id)
    tenant_id = str(org_id)
    genders = {"all": (), "male": (1,), "female": (2,)}[body.gender]
    categories = () if body.special_ad_category == "NONE" else (body.special_ad_category,)
    # Meta start_time/end_time 매핑 — 시작이 과거면 now로 끌어올림(writer가 추가로 24h 보정).
    start_at = datetime.strptime(body.start_date, "%Y-%m-%d").replace(tzinfo=UTC)
    if start_at < now:
        start_at = now
    end_at = (
        datetime.strptime(body.end_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if body.end_date
        else start_at + timedelta(days=7)
    )
    if end_at <= start_at:
        raise HTTPException(status_code=422, detail="종료일은 시작일 이후여야 합니다.")
    run_days = max(1, (end_at - start_at).days)  # spend_cap 산정용(일예산 × 일수)
    config = CampaignConfig(
        campaign_id=f"camp_sim_{uuid4().hex[:8]}",
        tenant_id=tenant_id,
        ad_account_id=ad_account,
        name=body.name,
        objective="traffic",
        daily_budget_krw=body.daily_budget_krw,
        start_at=start_at,
        end_at=end_at,
        image_hash=image_hash,
        headline=title,
        body=copy_text,
        link_url=link_url,
        special_ad_categories=categories,
        countries=(body.country,),
        age_min=body.age_min,
        age_max=body.age_max,
        genders=genders,
    )
    snapshot = {
        "simulation_id": body.simulation_id,
        "source_ad_id": str(ad_id),
        "verdict": "집행 권장",
        "source_asset": s3_key,
        "image_hash": image_hash,
        "headline": title,
        "body": copy_text,
        "click_intent_rate": cir,
        "rejection_rate": rej,
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
                "simulation_snapshot": snapshot,
            },
            metrics_as_of=now,
            hypothesis="시뮬 기반 신규 캠페인",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=0,
            budget_after_krw=body.daily_budget_krw,
            max_total_spend_krw=body.daily_budget_krw * run_days,
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


_require_org_id = require_user_org  # core.auth 공용(없으면 409) — 라우터 복붙 제거


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


# ── org 스코프 Meta 리더/라이터 — 로그인 org의 연결(토큰·계정)로 멀티테넌시 정합 ──
# mock 모드는 전역 mock 유지. live는 org 연결 자격증명(load_credentials) 기반 — 미연결이면 None.
_NOT_CONNECTED_MSG = "Meta 광고 계정이 연결되지 않았어요. 연결 후 다시 시도하세요."


async def _org_credentials(db: AsyncSession, org_id: UUID) -> MetaCredentials | None:
    """org 연결의 Meta 자격증명(복호화) — build_meta_client 드롭인. 키/연결 없으면 None."""
    key = getattr(settings, "meta_token_encryption_key", None)
    if not key:
        return None
    repo = MetaConnectionRepository(db, TokenCipher.from_base64_key(key))
    return await repo.load_credentials(org_id, settings)


async def _resolve_reader(db: AsyncSession, org_id: UUID) -> AdPlatformReader | None:
    """org 스코프 리더 — mock이면 전역 mock, live면 org 연결 기반(미연결이면 None)."""
    if getattr(settings, "use_mock", True):
        return build_reader(settings)
    creds = await _org_credentials(db, org_id)
    if creds is None:
        return None
    from domain.management.adapters.meta.reader import MetaAdsReader  # noqa: PLC0415

    return MetaAdsReader(creds)


async def _resolve_writer(db: AsyncSession, org_id: UUID) -> AdPlatformWriter | None:
    """org 스코프 라이터 — mock이면 전역 DRY_RUN, live면 org 연결 기반(미연결이면 None)."""
    if getattr(settings, "use_mock", True):
        return build_writer(settings)
    creds = await _org_credentials(db, org_id)
    if creds is None:
        return None
    from domain.management.adapters.meta.client import build_meta_client  # noqa: PLC0415
    from domain.management.adapters.meta.writer import MetaAdsWriter  # noqa: PLC0415

    # 실행모드·page_id·create_ad는 settings에서, 실제 API 호출은 org 연결 client로 주입한다.
    # creds엔 management_execution_mode가 없어 그대로 넘기면 LIVE라도 DRY_RUN으로 강등됨.
    return MetaAdsWriter(settings, client=build_meta_client(creds))


async def _require_reader(db: AsyncSession, org_id: UUID) -> AdPlatformReader:
    """org 리더 — 미연결이면 409 (fail-closed: 남의 전역 계정 노출 금지)."""
    reader = await _resolve_reader(db, org_id)
    if reader is None:
        raise HTTPException(409, _NOT_CONNECTED_MSG)
    return reader


async def _require_writer(db: AsyncSession, org_id: UUID) -> AdPlatformWriter:
    """org 라이터 — 미연결이면 409 (fail-closed)."""
    writer = await _resolve_writer(db, org_id)
    if writer is None:
        raise HTTPException(409, _NOT_CONNECTED_MSG)
    return writer


async def _require_owned_run(
    escalation: EscalationController, run_id: str, org_id: UUID
) -> EscalationRun:
    """사다리 run 소유 검증 — 없으면 404, 타 org면 403, 통과 시 run 반환."""
    run = await escalation.get_run(run_id)
    if run is None:
        raise HTTPException(404, "run을 찾을 수 없습니다.")
    if run.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 run입니다.")
    return run


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    body: ActivateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """게재 시작 — Meta 선불 잔액 게이트 → spend_cap → 캠페인·세트·광고 ACTIVE. 실과금 시작점."""
    org_id = await _require_org_id(user, db)
    row = await _require_owned_campaign(db, org_id, campaign_id)
    commit = body.commit_krw or (row.daily_budget_krw if row else 0)
    if commit <= 0:
        raise HTTPException(status_code=422, detail="배정 금액(commit_krw)을 결정할 수 없습니다.")

    # 0) 크레딧 한도 게이트 (LIVE만) — ClickMe 충전 크레딧이 배정액보다 적으면 차단.
    #    크레딧 = 예산 한도(인앱 /payment), Meta 선불 = 실광고비(Ads Manager). 두 충전 각각 게이트.
    credit_balance = 0
    if _resolved_execution_mode() is ExecutionMode.LIVE:
        from api.routers.billing import get_billing_service  # noqa: PLC0415 — 순환 방지

        credit_balance = await get_billing_service().balance(body.org_id)
        if credit_balance < commit:
            return {
                "serving": False,
                "result": None,
                "balance_krw": 0,
                "credit_krw": credit_balance,
                "commit_krw": commit,
                "causes": [
                    {
                        "code": "INSUFFICIENT_CREDIT",
                        "message": (
                            f"예산 한도(크레딧) 부족 — {commit - credit_balance:,}원 더 충전 필요. "
                            "충전 페이지에서 크레딧을 채우면 게재가 이어집니다."
                        ),
                        "need_krw": commit - credit_balance,
                        "credit_krw": credit_balance,
                        "commit_krw": commit,
                    }
                ],
            }

    # 1) 게이트 — Meta 광고계정 선불 잔액이 배정액보다 적으면 차단(실광고비 = Meta 선불).
    reader = await _require_reader(db, org_id)
    try:
        funding = await reader.get_account_funding()
        meta_balance = funding.available_balance_krw or 0
    except Exception:  # noqa: BLE001 — 자금 조회 실패 시 0으로 보아 차단(안전)
        meta_balance = 0
    if meta_balance < commit:
        return {
            "serving": False,
            "result": None,
            "balance_krw": meta_balance,
            "credit_krw": credit_balance,
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
    writer = await _require_writer(db, org_id)
    cap = await writer.set_spend_cap(campaign_id, commit, idem_key=f"cap_{uuid4().hex[:8]}")
    cap_status = cap.status.value if hasattr(cap.status, "value") else str(cap.status)
    if cap_status != "success":
        msg = _find_in_snapshot(cap.platform_response_snapshot, "user_msg")
        return {
            "serving": False,
            "result": cap.model_dump(mode="json"),
            "balance_krw": meta_balance,
            "credit_krw": credit_balance,
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
    ad_account = await _require_ad_account(db, org_id)
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=str(org_id),
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
    action = approve(proposal, str(user.id), execution_mode=_resolved_execution_mode())
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
        "credit_krw": credit_balance,
        "commit_krw": commit,
        "causes": [],
    }
    if not serving:
        msg = _find_in_snapshot(result.platform_response_snapshot, "user_msg")
        if msg:
            resp["error_message"] = str(msg)
    return resp


@router.get("/campaigns/{campaign_id}/delivery-status")
async def delivery_status(campaign_id: str, reader=Depends(_request_reader)):
    """게재 여부 + 불가 원인 + Meta 선불 잔액 — 대시보드/게재 화면이 원인을 그대로 표시."""
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
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Meta 누적 소진액 → 크레딧 차감 정산(증분) + 자동 종료 상태 반영."""
    org_uuid = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_uuid, campaign_id)
    org_id = str(org_uuid)
    reader = await _require_reader(db, org_uuid)
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
async def pause_campaign(
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 즉시 일시중지(PAUSED) — 게재·과금 중단. 크레딧 게이트 불요(돈이 나가는 쪽 아님)."""
    org_id = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_id, campaign_id)
    now = datetime.now(UTC)
    ad_account = await _require_ad_account(db, org_id)
    proposal = finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=str(org_id),
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
    action = approve(proposal, str(user.id), execution_mode=_resolved_execution_mode())
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
async def _budget_status(reader, budget_key: str = TENANT_ID) -> dict:
    # 실모드: 한도=월 목표 예산(관제), 소진=실 Meta 집행액. 크레딧·Meta 선불은 별도 필드.
    # budget_key는 인메모리 월 목표의 org별 키 — live는 org_id, mock은 TENANT_ID(전역 공유 방지).
    if not getattr(settings, "use_mock", True):
        return await _budget_status_live(reader, budget_key)
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


async def _budget_status_live(reader, budget_key: str = TENANT_ID) -> dict:
    """실데이터 예산 현황 — 월 목표 예산 대비 이번 달 실소진 페이싱(관제).

    reader는 호출자(로그인 org 연결)가 주입 — 멀티테넌시 정합.
    budget_key(org_id)별 월 목표 — 전역 TENANT_ID 공유 시 org끼리 목표가 섞이는 문제 방지.
    한도=월 목표 예산(설정), 소진=이번 달 Meta 집행, 잔여=목표−소진, 여력=Meta 선불 잔액.
    런레이트(projection)로 "이 페이스면 월말 얼마"를 예측한다. 캠페인별은 이번 달 소진·ROAS.
    """
    now = datetime.now(UTC)
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    target = _BUDGET.for_tenant(budget_key).limit_krw  # 월 목표(미설정 0) — org별 인메모리

    # 이번 달 실소진(계정 단위 1콜) + 일자별 곡선
    try:
        spent = await reader.get_account_spend("this_month")
    except Exception:  # noqa: BLE001 — 조회 실패면 0
        spent = 0
    try:
        daily = await reader.get_account_daily_spend("this_month")
    except Exception:  # noqa: BLE001
        daily = []
    # 여력 — Meta 선불 가용 잔액 + 충전 한도(spend_cap, 부가세 제외 집행가능액)·누적 지출.
    # 충전 한도 − 누적 지출 = 잔액으로 정합 표시(충전 한도는 결제액의 부가세 제외분).
    try:
        _funding = await reader.get_account_funding()
        account_balance = _funding.available_balance_krw or 0
        account_spend_cap = _funding.spend_cap_krw or 0
        account_amount_spent = _funding.amount_spent_krw or 0
    except Exception:  # noqa: BLE001
        account_balance = account_spend_cap = account_amount_spent = 0
    # ClickMe 크레딧 — 집행 한도(spend 권한)·잔액. 월 목표(관제)·Meta 선불(실광고비)과 별개 개념.
    try:
        _billing = get_billing_service()
        credit_charged = await _billing.total_charged(DEMO_ORG_ID)
        credit_balance = await _billing.balance(DEMO_ORG_ID)
    except Exception:  # noqa: BLE001 — 빌링 조회 실패면 0
        credit_charged = credit_balance = 0
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
        "account_balance_krw": account_balance,  # Meta 선불 잔액(실광고비)
        "account_spend_cap_krw": account_spend_cap,  # Meta 충전 한도(부가세 제외 집행가능액)
        "account_amount_spent_krw": account_amount_spent,  # Meta 누적 지출
        "credit_charged_krw": credit_charged,  # ClickMe 크레딧 총 충전(집행 한도)
        "credit_balance_krw": credit_balance,  # ClickMe 크레딧 잔액
        "period": now.strftime("%Y-%m"),
        "daily": daily,
        "decision": decision,
        "thresholds": {"warn": WARN_THRESHOLD, "escalate": ESCALATE_THRESHOLD},
        "campaigns": campaigns,
    }


@router.get("/budget")
async def get_budget(
    reader=Depends(_request_reader),
    user: User | None = Depends(_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """org 예산 한도 대비 캠페인 합산 소진 + 90/95/100% 판정 (월 목표는 org별)."""
    budget_key = TENANT_ID
    if not getattr(settings, "use_mock", True) and user is not None:
        budget_key = str(await _require_org_id(user, db))
    return await _budget_status(reader, budget_key)


class BudgetLimitRequest(BaseModel):
    limit_krw: int = Field(ge=0)


@router.post("/budget/limit")
async def set_budget_limit(
    body: BudgetLimitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """예산 한도 설정 — 변경 후 경고 레벨(decision)이 즉시 반영(인메모리)."""
    org_id = await _require_org_id(user, db)
    if getattr(settings, "use_mock", True):
        _BUDGET.set_limit(TENANT_ID, body.limit_krw)
        return await _budget_status(build_reader(settings))
    _BUDGET.set_limit(str(org_id), body.limit_krw)  # org별 월 목표(전역 공유 금지)
    return await _budget_status(await _require_reader(db, org_id), str(org_id))


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
    campaign_id: str = CAMPAIGN_ID
    now: str | None = None  # ISO8601 — 데모 tick(시간 전진)


@router.post("/re-evaluate")
async def re_evaluate(
    body: ReEvaluateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사다리 1회 재평가 — 개시/다음단계 제안 / 보류(PENDING) / 회복 / 소진을 반환."""
    org_id = await _require_org_id(user, db)
    ad_account = await _require_ad_account(db, org_id)
    outcome = await _get_escalation().re_evaluate(
        str(org_id), ad_account, body.campaign_id, now=_now_or(body.now)
    )
    return _escalation_payload(outcome)


class RungOutcomeRequest(BaseModel):
    run_id: str
    now: str | None = None
    approval_id: str | None = None


@router.post("/re-evaluate/executed")
async def mark_rung_executed(
    body: RungOutcomeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 단계가 집행됐음을 사다리에 알린다 (다음 재평가에서 회복 판정 가능)."""
    org_id = await _require_org_id(user, db)
    escalation = _get_escalation()
    await _require_owned_run(escalation, body.run_id, org_id)
    await escalation.on_executed(body.run_id, now=_now_or(body.now), approval_id=body.approval_id)
    return {"run_id": body.run_id, "rung_status": "executed"}


@router.post("/re-evaluate/rejected")
async def mark_rung_rejected(
    body: RungOutcomeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 단계가 거절됐음을 알린다 (다음 재평가에서 즉시 다음 단계로 에스컬레이션)."""
    org_id = await _require_org_id(user, db)
    escalation = _get_escalation()
    await _require_owned_run(escalation, body.run_id, org_id)
    await escalation.on_rejected(body.run_id)
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
