# Meta OAuth — 로그인 URL 생성 + code→장기토큰 교환 (MockTransport로 그래프 호출 대역)
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from domain.management.adapters.meta.client import MetaApiError
from domain.management.adapters.meta.oauth import (
    OAuthToken,
    build_login_url,
    exchange_code_for_token,
    exchange_for_long_lived,
)


def test_build_login_url_has_required_params():
    url = build_login_url(
        app_id="app1",
        redirect_uri="https://clickme.co.kr/api/management/meta/callback",
        scopes=["ads_read", "instagram_manage_insights"],
        state="org_7:csrf-nonce",
        api_version="v23.0",
    )
    parts = urlsplit(url)
    assert parts.netloc == "www.facebook.com"
    assert parts.path == "/v23.0/dialog/oauth"
    q = parse_qs(parts.query)
    assert q["client_id"] == ["app1"]
    assert q["response_type"] == ["code"]
    assert q["state"] == ["org_7:csrf-nonce"]
    # 스코프는 콤마로 결합
    assert q["scope"] == ["ads_read,instagram_manage_insights"]


def _transport(captured: dict, payload: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


async def test_exchange_code_for_token():
    captured = {}
    transport = _transport(
        captured, {"access_token": "short-tok", "token_type": "bearer", "expires_in": 3600}
    )
    tok = await exchange_code_for_token(
        app_id="app1",
        app_secret="sec1",
        redirect_uri="https://clickme.co.kr/cb",
        code="the-code",
        transport=transport,
        api_version="v23.0",
    )
    assert isinstance(tok, OAuthToken)
    assert tok.access_token == "short-tok"
    assert tok.expires_in == 3600
    # 올바른 엔드포인트·파라미터로 호출됐는지
    assert "/v23.0/oauth/access_token" in captured["url"]
    assert captured["params"]["code"] == "the-code"
    assert captured["params"]["client_secret"] == "sec1"


async def test_exchange_for_long_lived():
    captured = {}
    transport = _transport(
        captured, {"access_token": "long-tok", "token_type": "bearer", "expires_in": 5184000}
    )
    tok = await exchange_for_long_lived(
        app_id="app1",
        app_secret="sec1",
        short_lived_token="short-tok",
        transport=transport,
        api_version="v23.0",
    )
    assert tok.access_token == "long-tok"
    assert tok.expires_in == 5184000
    assert captured["params"]["grant_type"] == "fb_exchange_token"
    assert captured["params"]["fb_exchange_token"] == "short-tok"


async def test_exchange_surfaces_meta_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"code": 100, "message": "bad code"}})

    with pytest.raises(MetaApiError):
        await exchange_code_for_token(
            app_id="app1",
            app_secret="sec1",
            redirect_uri="https://clickme.co.kr/cb",
            code="bad",
            transport=httpx.MockTransport(handler),
            api_version="v23.0",
        )
