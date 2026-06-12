"""크레딧 결제 서비스 — 금액 대조·멱등 confirm·원장·잔액 보증 검증."""

import pytest

from domain.billing.service.billing_service import (
    BillingError,
    BillingService,
    LedgerReason,
    PaymentStatus,
)
from domain.billing.toss_client import (
    LiveKeyForbiddenError,
    PaymentConfirmError,
    require_test_key,
)

ORG = "org-demo"


class FakeToss:
    """토스 confirm 호출 대역 — 실네트워크 없음."""

    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    async def confirm(self, payment_key, order_id, amount_krw):
        self.calls.append((payment_key, order_id, amount_krw))
        if self.fail:
            raise PaymentConfirmError("토스 승인 거절(테스트)")
        return {"paymentKey": payment_key, "orderId": order_id, "totalAmount": amount_krw}


def make_service(fail=False) -> tuple[BillingService, FakeToss]:
    toss = FakeToss(fail=fail)
    return BillingService(toss), toss


async def test_charge_increases_balance():
    service, toss = make_service()
    order = service.create_order(ORG, 50_000)

    confirmed = await service.confirm("pay-1", order.order_id, 50_000)

    assert confirmed.status is PaymentStatus.DONE
    assert service.balance(ORG) == 50_000
    assert len(toss.calls) == 1
    assert service.history(ORG)[-1].reason is LedgerReason.CHARGE


async def test_amount_mismatch_is_rejected_without_toss_call():
    """FE가 보낸 금액 변조 → 서버 기억 금액과 대조해 차단."""
    service, toss = make_service()
    order = service.create_order(ORG, 50_000)

    with pytest.raises(BillingError, match="금액 불일치"):
        await service.confirm("pay-1", order.order_id, 999_999)

    assert service.balance(ORG) == 0
    assert toss.calls == []  # 토스 호출 전에 차단


async def test_duplicate_confirm_is_idempotent():
    """같은 paymentKey confirm 2회 → 원장 1건 (충전 중복 방지)."""
    service, toss = make_service()
    order = service.create_order(ORG, 30_000)

    first = await service.confirm("pay-1", order.order_id, 30_000)
    second = await service.confirm("pay-1", order.order_id, 30_000)

    assert first.order_id == second.order_id
    assert service.balance(ORG) == 30_000
    assert len(service.history(ORG)) == 1
    assert len(toss.calls) == 1


async def test_done_order_with_different_payment_key_is_rejected():
    service, _ = make_service()
    order = service.create_order(ORG, 30_000)
    await service.confirm("pay-1", order.order_id, 30_000)

    with pytest.raises(BillingError, match="이미 다른 결제"):
        await service.confirm("pay-2", order.order_id, 30_000)


async def test_unknown_order_is_rejected():
    service, _ = make_service()
    with pytest.raises(BillingError, match="존재하지 않는"):
        await service.confirm("pay-1", "no-such-order", 10_000)


async def test_toss_failure_marks_order_failed_and_keeps_ledger():
    service, _ = make_service(fail=True)
    order = service.create_order(ORG, 50_000)

    with pytest.raises(PaymentConfirmError):
        await service.confirm("pay-1", order.order_id, 50_000)

    assert order.status is PaymentStatus.FAILED
    assert service.balance(ORG) == 0
    assert service.history(ORG) == ()


def test_order_amount_must_be_positive_int():
    service, _ = make_service()
    with pytest.raises(BillingError):
        service.create_order(ORG, 0)
    with pytest.raises(BillingError):
        service.create_order(ORG, -1)


async def test_record_spend_decreases_balance_and_blocks_overdraft():
    service, _ = make_service()
    order = service.create_order(ORG, 50_000)
    await service.confirm("pay-1", order.order_id, 50_000)

    entry = service.record_spend(ORG, 30_000, ref_id="appr-1")

    assert entry.reason is LedgerReason.SPEND
    assert service.balance(ORG) == 20_000
    with pytest.raises(BillingError, match="잔액 부족"):
        service.record_spend(ORG, 20_001, ref_id="appr-2")
    assert service.balance(ORG) == 20_000  # 거부 건은 원장 무변화


def test_balances_are_isolated_per_org():
    service, _ = make_service()
    assert service.balance("org-a") == 0
    assert service.balance("org-b") == 0


def test_live_key_is_forbidden():
    """실돈 방지 가드 — 라이브 키는 기동 단계에서 거부 (7/8 Won't)."""
    assert require_test_key("test_gsk_docs_abc") == "test_gsk_docs_abc"
    with pytest.raises(LiveKeyForbiddenError):
        require_test_key("live_gsk_real_key")
