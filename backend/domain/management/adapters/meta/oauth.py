# 🅰 Meta OAuth(Facebook Login) — 로그인 URL 생성 + code→장기토큰 교환 (멀티테넌트 (B))
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from domain.management.adapters.meta.client import MetaClient

_DIALOG_BASE = "https://www.facebook.com"
_GRAPH_BASE = "https://graph.facebook.com"
_TIMEOUT = 30.0


@dataclass(frozen=True)
class OAuthToken:
    """OAuth 토큰 교환 결과. expires_in은 초(장기토큰 ~5184000=60일, 0이면 만료정보 없음)."""

    access_token: str
    token_type: str
    expires_in: int


def build_login_url(
    *,
    app_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str,
    api_version: str = "v21.0",
) -> str:
    """Facebook 로그인 대화상자 URL — /meta/connect가 여기로 redirect한다.

    state는 CSRF 방지 겸 콜백에서 어느 org의 연결인지 식별하는 용도. scopes는 App Review
    승인 권한과 일치해야 한다(콤마 결합).
    """
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "scope": ",".join(scopes),
        "state": state,
        "response_type": "code",
    }
    return f"{_DIALOG_BASE}/{api_version}/dialog/oauth?{urlencode(params)}"


async def exchange_code_for_token(
    *,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    code: str,
    transport: httpx.AsyncBaseTransport | None = None,
    api_version: str = "v21.0",
) -> OAuthToken:
    """콜백으로 받은 code를 단기 액세스 토큰으로 교환."""
    return await _oauth_get(
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
        transport=transport,
        api_version=api_version,
    )


async def exchange_for_long_lived(
    *,
    app_id: str,
    app_secret: str,
    short_lived_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
    api_version: str = "v21.0",
) -> OAuthToken:
    """단기 토큰을 장기 토큰(~60일)으로 교환 — 저장 대상."""
    return await _oauth_get(
        {
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
        transport=transport,
        api_version=api_version,
    )


async def _oauth_get(
    params: dict[str, str],
    *,
    transport: httpx.AsyncBaseTransport | None,
    api_version: str,
) -> OAuthToken:
    url = f"{_GRAPH_BASE}/{api_version}/oauth/access_token"
    async with httpx.AsyncClient(timeout=_TIMEOUT, transport=transport) as client:
        res = await client.get(url, params=params)
        payload = MetaClient._handle(res)  # 에러 표준화(MetaApiError) 재사용
    return OAuthToken(
        access_token=payload["access_token"],
        token_type=payload.get("token_type", "bearer"),
        expires_in=int(payload.get("expires_in", 0)),
    )
