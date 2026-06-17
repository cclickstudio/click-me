"""🤝 매니지먼트 얇은 엔드포인트 — 감지·진단·승인(HITL) 플로우 노출.

오케스트레이터('입')의 소유는 미정(R&R §6) — 본 라우터는 데모용 최소 구현이며
판정 로직은 전부 domain.management(approval.py 등)에 위임한다.
무상태(stateless): 프론트가 받은 제안을 그대로 돌려보내고, proposal_hash 재검증으로
변조를 감지한다 (승인 전 3단계 검증 시연).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings
from domain.management.adapters.mock import MockAdPlatform
from domain.management.agents.regeneration import RegenerationContext
from domain.management.agents.regeneration_tools import build_regeneration_agent
from domain.management.approval import (
    approve,
    relabel_if_mismatch,
    requires_human,
    validate_proposal,
)
from domain.management.comparison.service.comparison_service import ComparisonService
from domain.management.contracts.fault_injection import FaultConfig, FaultMode
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION, DAILY_BUDGET_KRW
from domain.management.contracts.schemas import (
    ActionProposal,
    ApprovedAction,
    DiagnosisResult,
    MetricsSnapshot,
)
from domain.management.demo import CAMPAIGN_ID, TENANT_ID, build_sample_proposal
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)
from domain.management.execution.executor import Executor
from domain.management.execution.tier import TenantBudgetRegistry
from domain.management.wiring import (
    build_audit_sink,
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
    snapshots = build_reader(settings).fetch_hourly_metrics(CAMPAIGN_ID, today, fault_cfg)
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
    context = RegenerationContext(
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
        snaps = self._mock.fetch_hourly_metrics(campaign_id, since, None, self._budget)
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


@router.get("/compare/board")
async def compare_board():
    """여러 게시물의 오가닉→광고 증분 일괄 검증 (B 뷰). 오가닉 reader는 공유해 행마다 다르게."""
    organic_reader = build_organic_reader(settings)  # 공유 → rng 진행되며 행별 상이
    since = _today_utc()
    rows = []
    for title, post_id, campaign_id, budget in _BOARD_DEMO:
        svc = ComparisonService(organic_reader, _MockAdSnapshotReader(daily_budget_krw=budget))
        lift = await svc.compare(post_id, campaign_id, since)
        rows.append({"title": title, "lift": lift.model_dump(mode="json")})
    return {"rows": rows}
