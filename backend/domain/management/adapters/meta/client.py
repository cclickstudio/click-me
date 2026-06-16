# 🤝 Meta 인증·토큰·HTTP 공통층 + 토큰 마스킹 (게이트 #8 — 민감값 평문 노출 금지)
"""Graph API 비동기 호출 공통층.

reader(🅰)·writer(🅱)가 공유한다. 토큰·앱 시크릿은 어떤 로그·예외 메시지에도
평문으로 나가지 않도록 ``_mask`` 를 거친다 (구조·역할 문서 §7 게이트 #8).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger("clickme")

_GRAPH_HOST = "https://graph.facebook.com"


def mask_secret(text: str, secret: str | None) -> str:
    """단일 비밀값을 앞6·뒤4만 남기고 가린다."""
    if secret and len(secret) > 10 and secret in text:
        return text.replace(secret, f"{secret[:6]}…{secret[-4:]}")
    return text


class MetaTokenError(RuntimeError):
    """토큰/앱 자격 미설정 — 메시지에 비밀값 없음."""


class MetaApiError(RuntimeError):
    """Graph API 호출 실패 — 메시지는 항상 마스킹된 상태."""


class MetaClient:
    """Graph API 호출 공통층. 어댑터는 이 클래스만 통해 외부에 나간다."""

    def __init__(
        self, settings: object, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._token: str | None = getattr(settings, "meta_access_token", None)
        version: str = getattr(settings, "meta_graph_api_version", None) or "v21.0"
        self._base = f"{_GRAPH_HOST}/{version}"
        self._app_id: str | None = getattr(settings, "meta_app_id", None)
        self._app_secret: str | None = getattr(settings, "meta_app_secret", None)
        self._transport = transport
        # 마스킹 대상 비밀값 목록 (토큰 + 앱 시크릿)
        self._secrets = [s for s in (self._token, self._app_secret) if s]

    def _mask(self, text: str) -> str:
        for secret in self._secrets:
            text = mask_secret(text, secret)
        return text

    @property
    def app_access_token(self) -> str:
        """app_id|app_secret — 토큰 디버그용 (⑤)."""
        if not (self._app_id and self._app_secret):
            raise MetaTokenError("META_APP_ID/META_APP_SECRET 미설정 — 앱 토큰 생성 불가")
        return f"{self._app_id}|{self._app_secret}"

    async def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self._request("POST", path, data=data)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self._token:
            raise MetaTokenError("META_ACCESS_TOKEN 미설정 — backend/.env 확인")
        url = f"{self._base}/{path.lstrip('/')}"
        # access_token 기본 주입 → 호출자 params가 덮어쓸 수 있음(앱 토큰 등).
        auth: dict[str, Any] = {"access_token": self._token}
        try:
            async with httpx.AsyncClient(timeout=30.0, transport=self._transport) as client:
                if method == "GET":
                    resp = await client.get(url, params={**auth, **(params or {})})
                else:
                    resp = await client.post(url, data={**auth, **(data or {})})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            body = self._mask(exc.response.text)
            raise MetaApiError(f"Meta API {exc.response.status_code}: {body}") from None
        except httpx.HTTPError as exc:
            raise MetaApiError(self._mask(str(exc))) from None

    async def debug_token(self) -> dict[str, Any]:
        """⑤ 토큰 검증 — 만료·스코프·유효성 조회 (앱 토큰으로 입력 토큰 점검)."""
        payload = await self.get(
            "debug_token",
            {"input_token": self._token, "access_token": self.app_access_token},
        )
        return payload.get("data", payload)
