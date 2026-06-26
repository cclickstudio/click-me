# 챗 카드 proposal_preview → 정본 finalize → (decision에서) approve/execute. 정본 본문은 서버에만.
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.management import _require_ad_account, _require_org_id
from core.auth import User, get_current_user
from core.config import settings
from core.db import AsyncSessionLocal, get_db
from core.models import ManagementChatMessage
from domain.management.approval import approve, judge_tier
from domain.management.assistant.chat_cards.models import (
    ChatCard,
    ExecutionResultSection,
    TraceInfo,
)
from domain.management.assistant.contracts import FinalizeResult
from domain.management.assistant.result_card import (
    build_execution_result_card,
    map_result_status,
)
from domain.management.assistant.tools import live_diagnosis
from domain.management.contracts.enums import ExecutionMode, ProposalStatus
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.contracts.schemas import AUTO_APPROVER, ActionResult
from domain.management.demo import TENANT_ID
from domain.management.execution.proposal_builder import (
    build_action_proposal_from_diagnosis,
    requires_external_approval,
)
from domain.management.execution.service.proposal_store import DbProposalStore, ProposalStore

router = APIRouter()

_TTL = timedelta(minutes=10)


def _get_proposal_store() -> ProposalStore:
    """프로덕션은 DbProposalStore. 테스트는 이 함수를 monkeypatch해 공유 InMemory 스토어 주입."""
    return DbProposalStore()


async def _persist_card(thread_id: str, card: ChatCard) -> None:
    """결과 카드를 management_chat_messages에 1건 적재(role=assistant, content=카드 JSON).

    자체 짧은 세션(db_stores 패턴). 테스트는 이 함수를 monkeypatch해 DB 없이 검증."""
    async with AsyncSessionLocal() as session:
        session.add(
            ManagementChatMessage(
                thread_id=thread_id,
                role="assistant",
                content=json.dumps(card.model_dump(mode="json"), ensure_ascii=False),
            )
        )
        await session.commit()


class FinalizeRequest(BaseModel):
    preview_id: str | None = None
    campaign_id: str
    thread_id: str | None = None
    shown_budget_after_krw: int | None = None
    shown_at: str | None = None
    preview_fingerprint: str | None = None


async def _resolve_tenant_account(user: User, db: AsyncSession) -> tuple[str, str]:
    if getattr(settings, "use_mock", True):
        return TENANT_ID, "act_demo"
    org_id = await _require_org_id(user, db)
    return str(org_id), await _require_ad_account(db, org_id)


@router.post("/proposals/finalize")
async def finalize_proposal_endpoint(
    body: FinalizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinalizeResult:
    tenant_id, ad_account_id = await _resolve_tenant_account(user, db)
    # NOTE(spec3 한계): live 모드 live_diagnosis는 build_reader(settings)(전역 스코프)로 읽어
    # 진단을 org 계정에 한정하지 않는다(기존 경로 공통 제약, Meta 멀티테넌트 후속).
    # 실지출 게이트는 decision/execute의 tenant 검사라 cross-tenant 집행은 차단된다.
    dx = await live_diagnosis(settings, body.campaign_id, tenant_id)
    if dx.diagnostic_status != "ok":
        return FinalizeResult(status="unavailable", reason=dx.reason or "진단할 수 없어요.")
    if not dx.anomaly or dx.proposal_preview is None:
        return FinalizeResult(status="no_anomaly", reason="더 이상 조치가 필요한 이상이 없어요.")

    now = datetime.now(UTC)
    proposal = build_action_proposal_from_diagnosis(
        dx,
        tenant_id=tenant_id,
        ad_account_id=ad_account_id,
        campaign_id=body.campaign_id,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        preview_id=body.preview_id,
        ttl=_TTL,
        now=now,
    )
    await _get_proposal_store().save(proposal)

    drift = (
        body.shown_budget_after_krw is not None
        and body.shown_budget_after_krw != proposal.budget_after_krw
    )
    return FinalizeResult(
        status="finalized",
        proposal_id=proposal.proposal_id,
        action_type=proposal.action_type,
        tier=proposal.action_tier.name,
        requires_external_approval=requires_external_approval(proposal.action_tier),
        budget_before_krw=proposal.budget_before_krw,
        budget_after_krw=proposal.budget_after_krw,
        summary=f"{proposal.action_type} 제안을 준비했어요.",
        expires_at=proposal.expires_at.isoformat(),
        drift=drift,
    )


class DecisionRequest(BaseModel):
    # FIX #1: Literal 제한 — approve/reject 외 값은 422 차단(execute 미진입, fail-open 방지).
    decision: Literal["approve", "reject"]
    idempotency_key: str
    thread_id: str | None = None


async def _execute(
    approved,
    proposal,
    idempotency_key: str,
    *,
    db: AsyncSession | None = None,
    org_id: str | None = None,
) -> ActionResult:
    """executor 호출 격리 지점(테스트 monkeypatch). 기존 /execute와 동일 executor·writer 선택.

    cross-request 정확히-1회는 try_claim이 보장(executor 내부 키는 approval_id 파생).
    live·비데모는 /execute와 동일하게 org 연결 writer로 집행(전역 executor가 아니라).
    """
    from api.routers.management import _get_executor, _require_writer

    # /execute와 동일 패턴 — 데모(TENANT_ID 센티넬)·mock은 전역 DRY_RUN executor,
    # 실 제안(live)은 로그인 org 연결 writer로 집행.
    is_demo = proposal.tenant_id == TENANT_ID
    if is_demo or getattr(settings, "use_mock", True) or db is None or org_id is None:
        executor = _get_executor()
    else:
        executor = _get_executor(await _require_writer(db, org_id))
    return await executor.execute(approved, proposal)


def _exec_mode() -> ExecutionMode:
    from api.routers.management import _resolved_execution_mode

    return _resolved_execution_mode()


def _new_turn_id() -> str:
    return f"turn_{uuid4().hex[:12]}"  # 카드 trace id — thread/session id와 분리


def _terminal_card(proposal, result_status: str, turn_id: str) -> ChatCard:
    return build_execution_result_card(
        proposal=proposal,
        result=None,
        run_id=None,
        turn_id=turn_id,
        result_status=result_status,
    )


def _safe_expired(proposal_id: str, turn_id: str) -> ChatCard:
    return ChatCard(
        type="management",
        status="neutral",
        sections=[
            ExecutionResultSection(
                title="집행 결과",
                action_type="UNKNOWN",
                result_status="expired",
                proposal_id=proposal_id,
                summary="제안을 찾을 수 없어요. 다시 검토를 요청해 주세요.",
            )
        ],
        trace=TraceInfo(turn_id=turn_id),
    )


@router.post("/proposals/{proposal_id}/decision")
async def decide_proposal(
    proposal_id: str,
    body: DecisionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatCard:
    # 결정 로직은 _decide가 결과 카드를 반환하고, 여기서 세션 thread_id로 이력 적재 후 반환.
    # 적재 키는 세션 thread_id(카드의 turn_id 아님) — 세션 재조회 시 결과 카드를 복원하기 위함.
    card = await _decide(proposal_id, body, user, db)
    await _persist_card(body.thread_id or proposal_id, card)
    return card


async def _decide(
    proposal_id: str,
    body: DecisionRequest,
    user: User,
    db: AsyncSession,
) -> ChatCard:
    """결정 가드 로직 — 모든 종결 분기에서 결과 카드를 반환(부수효과 영속은 호출자가 담당).

    가드 순서/로직은 변경 금지(tenant→reject→Tier3→executed→expired→try_claim→approve→execute)."""
    tenant_id, _ = await _resolve_tenant_account(user, db)  # execute 시점 authz
    store = _get_proposal_store()
    proposal = await store.get(proposal_id)
    turn_id = _new_turn_id()

    if proposal is None or proposal.tenant_id != tenant_id:
        return _safe_expired(proposal_id, turn_id)

    if body.decision == "reject":
        # FIX #6: 원자적 CAS reject — 동시 approve/claim과의 경합을 차단. 멱등(2회차도 rejected).
        await store.try_reject(proposal_id)
        return _terminal_card(proposal, "rejected", turn_id)

    # FIX #2: Tier3/chat-ineligible 서버 가드 — FE에만 기대지 않는다. approve() 전 즉시 차단.
    # action_tier 라벨은 proposal_hash에서 제외(_HASH_EXCLUDED)되어 변조·구화 가능 → 정책 권위
    # (judge_tier = TIER_POLICY)에서 action_type으로 정본 Tier를 재도출해 판정한다.
    if requires_external_approval(judge_tier(proposal.action_type)):
        return _terminal_card(proposal, "rejected", turn_id)

    if proposal.status == ProposalStatus.EXECUTED:
        return _terminal_card(proposal, "already_executed", turn_id)
    if proposal.expires_at < datetime.now(UTC):
        await store.set_status(proposal_id, ProposalStatus.EXPIRED)
        return _terminal_card(proposal, "expired", turn_id)

    # 원자적 claim — 동시/중복은 정확히 1회만 통과.
    if not await store.try_claim(proposal_id):
        return _terminal_card(proposal, "already_executed", turn_id)

    # NOTE(spec3 한계, FIX #4/#5): execute가 크래시하면 proposal이 APPROVED로 남아 재시도
    # 불가(다음 시도는 already_executed). 일시 실패도 REJECTED로 종결(재시도는 새 finalize).
    # 재시도/조정(reconciliation)은 후속 — spec3 non-goals.
    approved = approve(
        proposal,
        approver_id=str(getattr(user, "id", AUTO_APPROVER)),
        execution_mode=_exec_mode(),
    )
    # FIX #3: live·비데모는 /execute와 동일하게 org 연결 writer로 집행. tenant_id가 org_id(live).
    result = await _execute(approved, proposal, body.idempotency_key, db=db, org_id=tenant_id)
    rs = map_result_status(result.status, result.failure_reason)
    await store.set_status(
        proposal_id,
        ProposalStatus.EXECUTED
        if rs in ("success", "submitted_pending_review")
        else ProposalStatus.REJECTED,
    )
    return build_execution_result_card(
        proposal=proposal, result=result, run_id=None, turn_id=turn_id
    )
