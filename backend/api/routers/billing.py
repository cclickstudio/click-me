"""billing 라우터 — 크레딧 충전 결제 (토스 테스트 모드 전용).

management.py(🤝 공동)와 분리된 별도 라우터.
인증은 6.12 단계 미구현 → org_id는 데모 고정값(쿼리로 교체 가능).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from domain.billing.service.billing_service import BillingError, BillingService
from domain.billing.toss_client import PaymentConfirmError, TossPaymentsHttpClient

router = APIRouter()

DEMO_ORG_ID = "org-demo"

_service: BillingService | None = None


def get_billing_service() -> BillingService:
    """싱글턴 서비스 — 테스트는 dependency_overrides로 Fake 주입."""
    global _service  # noqa: PLW0603
    if _service is None:
        from core.config import settings  # noqa: PLC0415 — 테스트에서 settings 미로드 허용

        _service = BillingService(TossPaymentsHttpClient(settings.toss_secret_key))
    return _service


def get_client_key() -> str:
    from core.config import settings  # noqa: PLC0415

    return settings.toss_client_key


class OrderCreateRequest(BaseModel):
    amount_krw: int = Field(gt=0, description="충전 금액 (KRW 정수)")
    org_id: str = DEMO_ORG_ID


class OrderCreateResponse(BaseModel):
    order_id: str
    amount_krw: int
    client_key: str  # FE 위젯 초기화용 (테스트 키)


class ConfirmRequest(BaseModel):
    payment_key: str
    order_id: str
    amount_krw: int = Field(gt=0)


class ConfirmResponse(BaseModel):
    order_id: str
    status: str
    amount_krw: int
    balance_krw: int


class BalanceResponse(BaseModel):
    org_id: str
    balance_krw: int


@router.post("/orders", response_model=OrderCreateResponse)
async def create_order(
    body: OrderCreateRequest, service: BillingService = Depends(get_billing_service)
):
    try:
        order = service.create_order(body.org_id, body.amount_krw)
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return OrderCreateResponse(
        order_id=order.order_id, amount_krw=order.amount_krw, client_key=get_client_key()
    )


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm_payment(
    body: ConfirmRequest, service: BillingService = Depends(get_billing_service)
):
    try:
        order = await service.confirm(body.payment_key, body.order_id, body.amount_krw)
    except BillingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaymentConfirmError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ConfirmResponse(
        order_id=order.order_id,
        status=str(order.status),
        amount_krw=order.amount_krw,
        balance_krw=service.balance(order.org_id),
    )


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(
    org_id: str = DEMO_ORG_ID, service: BillingService = Depends(get_billing_service)
):
    return BalanceResponse(org_id=org_id, balance_krw=service.balance(org_id))


@router.get("/history")
async def get_history(
    org_id: str = DEMO_ORG_ID, service: BillingService = Depends(get_billing_service)
):
    return {
        "org_id": org_id,
        "entries": [
            {
                "entry_id": e.entry_id,
                "delta_krw": e.delta_krw,
                "balance_after_krw": e.balance_after_krw,
                "reason": str(e.reason),
                "ref_id": e.ref_id,
                "created_at": e.created_at.isoformat(),
            }
            for e in service.history(org_id)
        ],
    }
