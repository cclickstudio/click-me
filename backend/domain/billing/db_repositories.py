# 크레딧 결제 영속 어댑터 — 주문·원장을 NeonDB(async)에 저장 (db_stores.py 패턴)
"""BillingService의 InMemory Repository와 같은 Port를 구현해 wiring 지점에서 교체된다.

메서드당 짧은 세션(get_db 패턴)을 연다. core(db·models)는 공유 인프라라 import 허용.
원장은 append-only — UPDATE/DELETE 경로 없음.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import CreditLedgerRow, PaymentOrderRow
from domain.billing.service.billing_service import (
    LedgerEntry,
    LedgerReason,
    PaymentOrder,
    PaymentStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def _to_order(row: PaymentOrderRow) -> PaymentOrder:
    return PaymentOrder(
        order_id=row.order_id,
        org_id=row.org_id,
        amount_krw=row.amount_krw,
        status=PaymentStatus(row.status),
        payment_key=row.payment_key,
        raw_response=row.raw_response,
        cancel_response=row.cancel_response,
        created_at=row.created_at,
        approved_at=row.approved_at,
        canceled_at=row.canceled_at,
    )


class DbOrderRepository:
    """payment_orders 영속 — order_id PK 기준 upsert(merge)."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def get(self, order_id: str) -> PaymentOrder | None:
        async with self._sf() as session:
            row = await session.get(PaymentOrderRow, order_id)
            return _to_order(row) if row else None

    async def save(self, order: PaymentOrder) -> None:
        async with self._sf() as session:
            await session.merge(
                PaymentOrderRow(
                    order_id=order.order_id,
                    org_id=order.org_id,
                    amount_krw=order.amount_krw,
                    status=str(order.status),
                    payment_key=order.payment_key,
                    raw_response=order.raw_response,
                    cancel_response=order.cancel_response,
                    created_at=order.created_at,
                    approved_at=order.approved_at,
                    canceled_at=order.canceled_at,
                )
            )
            await session.commit()


class DbLedgerRepository:
    """credit_ledger 영속 — append-only(INSERT만). 잔액은 서비스가 delta 합으로 산출."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal
    ) -> None:
        self._sf = session_factory

    async def append(self, entry: LedgerEntry) -> None:
        async with self._sf() as session:
            session.add(
                CreditLedgerRow(
                    org_id=entry.org_id,
                    delta_krw=entry.delta_krw,
                    balance_after_krw=entry.balance_after_krw,
                    reason=str(entry.reason),
                    ref_id=entry.ref_id,
                    created_at=entry.created_at,
                )
            )
            await session.commit()

    async def entries(self, org_id: str) -> tuple[LedgerEntry, ...]:
        async with self._sf() as session:
            rows = (
                (
                    await session.execute(
                        select(CreditLedgerRow)
                        .where(CreditLedgerRow.org_id == org_id)
                        .order_by(CreditLedgerRow.id)
                    )
                )
                .scalars()
                .all()
            )
        return tuple(
            LedgerEntry(
                org_id=r.org_id,
                delta_krw=r.delta_krw,
                balance_after_krw=r.balance_after_krw,
                reason=LedgerReason(r.reason),
                ref_id=r.ref_id,
                entry_id=str(r.id),
                created_at=r.created_at,
            )
            for r in rows
        )
