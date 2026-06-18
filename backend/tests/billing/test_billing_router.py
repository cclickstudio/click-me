"""billing 라우터 — 엔드포인트 왕복 검증 (서비스는 Fake 토스 주입, api.main 미사용)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import billing
from domain.billing.service.billing_service import BillingService
from tests.billing.test_billing_service import FakeToss


@pytest.fixture()
def client(monkeypatch):
    app = FastAPI()
    app.include_router(billing.router, prefix="/api/billing")
    service = BillingService(FakeToss())
    app.dependency_overrides[billing.get_billing_service] = lambda: service
    monkeypatch.setattr(billing, "get_client_key", lambda: "test_gck_dummy")
    return TestClient(app)


def test_order_confirm_balance_roundtrip(client):
    created = client.post("/api/billing/orders", json={"amount_krw": 50_000}).json()
    assert created["client_key"].startswith("test_")

    confirmed = client.post(
        "/api/billing/confirm",
        json={
            "payment_key": "pay-1",
            "order_id": created["order_id"],
            "amount_krw": 50_000,
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["balance_krw"] == 50_000

    balance = client.get("/api/billing/balance").json()
    assert balance["balance_krw"] == 50_000

    history = client.get("/api/billing/history").json()
    assert len(history["entries"]) == 1
    assert history["entries"][0]["reason"] == "charge"


def test_confirm_amount_mismatch_returns_400(client):
    created = client.post("/api/billing/orders", json={"amount_krw": 10_000}).json()

    response = client.post(
        "/api/billing/confirm",
        json={
            "payment_key": "pay-1",
            "order_id": created["order_id"],
            "amount_krw": 99_999,
        },
    )
    assert response.status_code == 400
    assert "금액 불일치" in response.json()["detail"]


def test_order_rejects_non_positive_amount(client):
    response = client.post("/api/billing/orders", json={"amount_krw": 0})
    assert response.status_code == 422  # Pydantic gt=0
