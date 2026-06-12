"""크레딧 결제 서비스 — 주문 생성·승인(멱등)·원장·잔액.

핵심 보증:
- 금액은 서버가 기억한 주문과 대조한다 — FE가 보낸 금액 변조 차단.
- 같은 주문의 중복 confirm은 멱등 — 원장에 1건만 기록.
- 승인 실패 시 주문 FAILED, 원장 무변화.
- 영속화는 인메모리 Port — core 테이블 합의 후 Repository만 교체.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from domain.billing.toss_client import PaymentConfirmError, TossPaymentsClient


class PaymentStatus(StrEnum):
    READY = "ready"
    DONE = "done"
    FAILED = "failed"


class LedgerReason(StrEnum):
    CHARGE = "charge"  # 결제 충전
    SPEND = "spend"  # 광고 집행 차감


@dataclass
class PaymentOrder:
    order_id: str
    org_id: str
    amount_krw: int
    status: PaymentStatus = PaymentStatus.READY
    payment_key: str | None = None
    raw_response: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None


@dataclass(frozen=True)
class LedgerEntry:
    org_id: str
    delta_krw: int  # CHARGE는 양수, SPEND는 음수
    balance_after_krw: int
    reason: LedgerReason
    ref_id: str  # 주문 ID 또는 집행 참조
    entry_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BillingError(RuntimeError):
    """요청 거부 사유 — 라우터에서 HTTP 400으로 매핑."""


class OrderRepository(Protocol):
    def get(self, order_id: str) -> PaymentOrder | None: ...

    def save(self, order: PaymentOrder) -> None: ...


class LedgerRepository(Protocol):
    """append-only — 수정·삭제 경로 없음 (감사 로그와 동일 원칙)."""

    def append(self, entry: LedgerEntry) -> None: ...

    def entries(self, org_id: str) -> tuple[LedgerEntry, ...]: ...


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, PaymentOrder] = {}

    def get(self, order_id: str) -> PaymentOrder | None:
        return self._orders.get(order_id)

    def save(self, order: PaymentOrder) -> None:
        self._orders[order.order_id] = order


class InMemoryLedgerRepository:
    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def append(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def entries(self, org_id: str) -> tuple[LedgerEntry, ...]:
        return tuple(e for e in self._entries if e.org_id == org_id)


class BillingService:
    def __init__(
        self,
        toss: TossPaymentsClient,
        *,
        orders: OrderRepository | None = None,
        ledger: LedgerRepository | None = None,
    ) -> None:
        self._toss = toss
        self._orders = orders or InMemoryOrderRepository()
        self._ledger = ledger or InMemoryLedgerRepository()

    # ── 주문 ────────────────────────────────────────────────────

    def create_order(self, org_id: str, amount_krw: int) -> PaymentOrder:
        """충전 주문 생성 — 금액은 서버가 기억한다 (KRW 정수, 양수만)."""
        if not isinstance(amount_krw, int) or amount_krw <= 0:
            raise BillingError("충전 금액은 양의 KRW 정수여야 합니다")
        order = PaymentOrder(order_id=str(uuid4()), org_id=org_id, amount_krw=amount_krw)
        self._orders.save(order)
        return order

    async def confirm(self, payment_key: str, order_id: str, amount_krw: int) -> PaymentOrder:
        """결제 승인 확정 — 금액 대조 → 멱등 → 토스 confirm → 원장 CHARGE."""
        order = self._orders.get(order_id)
        if order is None:
            raise BillingError("존재하지 않는 주문입니다")
        if order.status is PaymentStatus.DONE:
            if order.payment_key == payment_key:
                return order  # 중복 confirm 멱등 재생
            raise BillingError("이미 다른 결제로 승인된 주문입니다")
        if amount_krw != order.amount_krw:
            raise BillingError(
                f"금액 불일치: 주문 {order.amount_krw}원 ≠ 요청 {amount_krw}원 (변조 의심)"
            )
        try:
            response = await self._toss.confirm(payment_key, order_id, amount_krw)
        except PaymentConfirmError:
            order.status = PaymentStatus.FAILED
            self._orders.save(order)
            raise
        order.status = PaymentStatus.DONE
        order.payment_key = payment_key
        order.raw_response = response
        order.approved_at = datetime.now(UTC)
        self._orders.save(order)
        self._ledger.append(
            LedgerEntry(
                org_id=order.org_id,
                delta_krw=order.amount_krw,
                balance_after_krw=self.balance(order.org_id) + order.amount_krw,
                reason=LedgerReason.CHARGE,
                ref_id=order.order_id,
            )
        )
        return order

    # ── 원장 ────────────────────────────────────────────────────

    def balance(self, org_id: str) -> int:
        entries = self._ledger.entries(org_id)
        return entries[-1].balance_after_krw if entries else 0

    def history(self, org_id: str) -> tuple[LedgerEntry, ...]:
        return self._ledger.entries(org_id)

    def record_spend(self, org_id: str, amount_krw: int, ref_id: str) -> LedgerEntry:
        """광고 집행 성공분 차감 — 잔액 초과 차단 (음수 잔액 금지)."""
        if not isinstance(amount_krw, int) or amount_krw <= 0:
            raise BillingError("차감 금액은 양의 KRW 정수여야 합니다")
        current = self.balance(org_id)
        if amount_krw > current:
            raise BillingError(f"잔액 부족: 잔액 {current}원 < 차감 {amount_krw}원")
        entry = LedgerEntry(
            org_id=org_id,
            delta_krw=-amount_krw,
            balance_after_krw=current - amount_krw,
            reason=LedgerReason.SPEND,
            ref_id=ref_id,
        )
        self._ledger.append(entry)
        return entry
