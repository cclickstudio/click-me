"""토스페이먼츠 결제 승인(confirm) 클라이언트 — 테스트 키 전용.

흐름: FE 위젯 결제 → successUrl 리다이렉트 → BE가 이 클라이언트로 승인 확정.
시크릿 키는 로그에 노출하지 않는다.
"""

from __future__ import annotations

import base64
from typing import Any, Protocol

import httpx

TOSS_API_BASE = "https://api.tosspayments.com"

#: 테스트 키 접두사 — 이 외의 키는 거부한다 (실돈 방지 가드)
TEST_KEY_PREFIXES = ("test_",)


class LiveKeyForbiddenError(RuntimeError):
    """라이브 키 주입 차단 — 실돈 결제는 7/8 스코프 제외 (Won't)."""


def require_test_key(key: str) -> str:
    if not key.startswith(TEST_KEY_PREFIXES):
        raise LiveKeyForbiddenError(
            "토스 라이브 키는 사용 불가 — 테스트 키(test_*)만 허용 (실돈 결제는 7/8 Won't)"
        )
    return key


class PaymentConfirmError(RuntimeError):
    """PG 승인 실패 — 주문은 FAILED로 기록되고 원장은 변하지 않는다."""


class TossPaymentsClient(Protocol):
    async def confirm(self, payment_key: str, order_id: str, amount_krw: int) -> dict[str, Any]:
        """결제 승인 확정 — 성공 시 토스 Payment 객체(dict) 반환, 실패 시 PaymentConfirmError."""
        ...


class TossPaymentsHttpClient:
    """실제 토스 API 호출 구현 — 테스트 시크릿 키 강제."""

    def __init__(self, secret_key: str, *, base_url: str = TOSS_API_BASE) -> None:
        self._secret_key = require_test_key(secret_key)
        self._base_url = base_url

    async def confirm(self, payment_key: str, order_id: str, amount_krw: int) -> dict[str, Any]:
        credential = base64.b64encode(f"{self._secret_key}:".encode()).decode()
        try:
            async with httpx.AsyncClient(base_url=self._base_url, timeout=10.0) as client:
                response = await client.post(
                    "/v1/payments/confirm",
                    headers={"Authorization": f"Basic {credential}"},
                    json={"paymentKey": payment_key, "orderId": order_id, "amount": amount_krw},
                )
        except httpx.HTTPError as exc:
            raise PaymentConfirmError(f"토스 API 통신 실패: {type(exc).__name__}") from exc
        if response.status_code != 200:
            detail = response.json().get("message", response.text)  # 시크릿 미포함 응답
            raise PaymentConfirmError(f"토스 승인 거절({response.status_code}): {detail}")
        return response.json()
