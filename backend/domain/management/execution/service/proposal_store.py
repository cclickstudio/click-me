# action_proposals 정본 영속 — InMemory(단위) / Db(prod). try_claim = 정확히-1회 원자 전이.
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import select, update

from core.db import AsyncSessionLocal
from core.models import ActionProposalRow
from domain.management.contracts.enums import ActionTier, ProposalStatus
from domain.management.contracts.schemas import ActionProposal

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class ProposalStore(Protocol):
    async def save(self, proposal: ActionProposal) -> None: ...
    async def get(self, proposal_id: str) -> ActionProposal | None: ...
    async def set_status(self, proposal_id: str, status: ProposalStatus) -> None: ...
    async def try_claim(self, proposal_id: str) -> bool: ...  # PENDING→APPROVED 1회만 True
    async def try_reject(self, proposal_id: str) -> bool: ...  # PENDING→REJECTED 1회만 True


class InMemoryProposalStore:
    def __init__(self) -> None:
        self._p: dict[str, ActionProposal] = {}

    async def save(self, proposal: ActionProposal) -> None:
        self._p[proposal.proposal_id] = proposal

    async def get(self, proposal_id: str) -> ActionProposal | None:
        return self._p.get(proposal_id)

    async def set_status(self, proposal_id: str, status: ProposalStatus) -> None:
        cur = self._p.get(proposal_id)
        if cur is not None:
            self._p[proposal_id] = cur.model_copy(update={"status": status})

    async def try_claim(self, proposal_id: str) -> bool:
        cur = self._p.get(proposal_id)
        if cur is None or cur.status != ProposalStatus.PENDING:
            return False
        self._p[proposal_id] = cur.model_copy(update={"status": ProposalStatus.APPROVED})
        return True

    async def try_reject(self, proposal_id: str) -> bool:
        cur = self._p.get(proposal_id)
        if cur is None or cur.status != ProposalStatus.PENDING:
            return False
        self._p[proposal_id] = cur.model_copy(update={"status": ProposalStatus.REJECTED})
        return True


def _to_row(p: ActionProposal) -> ActionProposalRow:
    return ActionProposalRow(
        proposal_id=p.proposal_id,
        tenant_id=p.tenant_id,
        ad_account_id=p.ad_account_id,
        action_type=p.action_type,
        action_tier=int(p.action_tier),
        status=p.status.value,
        budget_before_krw=p.budget_before_krw,
        budget_after_krw=p.budget_after_krw,
        max_total_spend_krw=p.max_total_spend_krw,
        expected_state_version=p.expected_state_version,
        proposal_hash=p.proposal_hash,
        approval_policy_version=p.approval_policy_version,
        expires_at=p.expires_at,
        payload={
            "evidence_metrics": p.evidence_metrics,
            "hypothesis": p.hypothesis,
            "confidence": p.confidence,
            "metrics_as_of": p.metrics_as_of.isoformat(),
            "target_object_ids": list(p.target_object_ids),
        },
    )


def _to_proposal(row: ActionProposalRow) -> ActionProposal:
    pl = row.payload or {}
    return ActionProposal(
        proposal_id=row.proposal_id,
        tenant_id=row.tenant_id,
        ad_account_id=row.ad_account_id,
        target_object_ids=tuple(pl.get("target_object_ids", [])),
        action_type=row.action_type,
        action_tier=ActionTier(row.action_tier),
        evidence_metrics=pl.get("evidence_metrics", {}),
        metrics_as_of=datetime.fromisoformat(pl["metrics_as_of"]),
        hypothesis=pl.get("hypothesis", ""),
        confidence=pl.get("confidence", 0.0),
        expected_state_version=row.expected_state_version,
        budget_before_krw=row.budget_before_krw,
        budget_after_krw=row.budget_after_krw,
        max_total_spend_krw=row.max_total_spend_krw,
        expires_at=row.expires_at,
        proposal_hash=row.proposal_hash,
        approval_policy_version=row.approval_policy_version,
        status=ProposalStatus(row.status),
    )


class DbProposalStore:
    """action_proposals 기반 — 메서드당 짧은 세션(get_db 패턴). try_claim = 게이트 #1."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def save(self, proposal: ActionProposal) -> None:
        async with self._sf() as session:
            session.add(_to_row(proposal))
            await session.commit()

    async def get(self, proposal_id: str) -> ActionProposal | None:
        async with self._sf() as session:
            row = (
                await session.execute(
                    select(ActionProposalRow).where(ActionProposalRow.proposal_id == proposal_id)
                )
            ).scalar_one_or_none()
        return _to_proposal(row) if row is not None else None

    async def set_status(self, proposal_id: str, status: ProposalStatus) -> None:
        async with self._sf() as session:
            await session.execute(
                update(ActionProposalRow)
                .where(ActionProposalRow.proposal_id == proposal_id)
                .values(status=status.value)
            )
            await session.commit()

    async def try_claim(self, proposal_id: str) -> bool:
        """원자적 PENDING→APPROVED. 정확히 1회만 True (동시/중복 가드, 게이트 #1)."""
        async with self._sf() as session:
            res = await session.execute(
                update(ActionProposalRow)
                .where(
                    ActionProposalRow.proposal_id == proposal_id,
                    ActionProposalRow.status == ProposalStatus.PENDING.value,
                )
                .values(status=ProposalStatus.APPROVED.value)
            )
            await session.commit()
            return res.rowcount == 1

    async def try_reject(self, proposal_id: str) -> bool:
        """원자적 PENDING→REJECTED. 동시 approve/claim과의 경합에서 정확히 1회만 True."""
        async with self._sf() as session:
            res = await session.execute(
                update(ActionProposalRow)
                .where(
                    ActionProposalRow.proposal_id == proposal_id,
                    ActionProposalRow.status == ProposalStatus.PENDING.value,
                )
                .values(status=ProposalStatus.REJECTED.value)
            )
            await session.commit()
            return res.rowcount == 1
