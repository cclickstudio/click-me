# Meta 연결 완료 오케스트레이션 — 토큰 교환 + granular_scopes 자산 조회 후 암호화 저장 (Mock+SQLite)
import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from core.models import MetaConnection
from domain.management.adapters.meta.connection_flow import complete_meta_connection
from domain.management.adapters.meta.connection_repository import MetaConnectionRepository
from domain.management.adapters.meta.token_crypto import TokenCipher, generate_key


async def _session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(MetaConnection.__table__.create)
    return AsyncSession(engine)


_DEBUG_TOKEN = {
    "data": {
        "scopes": ["ads_read", "ads_management", "pages_show_list", "instagram_basic"],
        "granular_scopes": [
            {"scope": "pages_show_list", "target_ids": ["page_1"]},
            {"scope": "instagram_basic", "target_ids": ["ig_1"]},
            {"scope": "ads_management", "target_ids": None},  # 전체 부여 → 추측 금지, 호출자 폴백
        ],
    }
}


def _flow_transport() -> httpx.MockTransport:
    """OAuth 토큰 교환 + debug_token을 URL로 분기."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        params = dict(request.url.params)
        if "/debug_token" in url:
            return httpx.Response(200, json=_DEBUG_TOKEN)
        if params.get("grant_type") == "fb_exchange_token":
            return httpx.Response(
                200, json={"access_token": "LONG", "token_type": "bearer", "expires_in": 5184000}
            )
        return httpx.Response(
            200, json={"access_token": "SHORT", "token_type": "bearer", "expires_in": 3600}
        )

    return httpx.MockTransport(handler)


async def test_complete_stores_token_and_granular_assets():
    cipher = TokenCipher.from_base64_key(generate_key())
    org = uuid.uuid4()
    async with await _session() as session:
        await complete_meta_connection(
            session,
            cipher,
            app_id="app1",
            app_secret="sec1",
            redirect_uri="https://clickme.co.kr/cb",
            code="the-code",
            organization_id=org,
            fallback_ad_account_id="act_env_default",
            transport=_flow_transport(),
        )
        repo = MetaConnectionRepository(session, cipher)
        assert await repo.load_token(org) == "LONG"
        row = await repo._get(org)
        assert "LONG" not in row.access_token_enc
        assert row.token_expires_at is not None
        # granular_scopes로 정확한 페이지·IG. ads는 계정이 안 묶여(전체 부여) 추측하지 않고
        # 호출자가 준 운영 기본 계정(fallback)으로 — 임의 첫 계정 바인딩 사고 방지.
        assert row.page_id == "page_1"
        assert row.ig_user_id == "ig_1"
        assert row.ad_account_id == "act_env_default"
        assert row.scopes == ["ads_read", "ads_management", "pages_show_list", "instagram_basic"]


async def test_assets_best_effort_when_calls_fail():
    # debug_token·adaccounts가 에러여도 연결(토큰 저장)은 성공해야 한다.
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "/debug_token" in url or "/me/" in url:
            return httpx.Response(400, json={"error": {"code": 10, "message": "no permission"}})
        params = dict(request.url.params)
        if params.get("grant_type") == "fb_exchange_token":
            return httpx.Response(
                200, json={"access_token": "LONG", "token_type": "bearer", "expires_in": 100}
            )
        return httpx.Response(
            200, json={"access_token": "SHORT", "token_type": "bearer", "expires_in": 100}
        )

    cipher = TokenCipher.from_base64_key(generate_key())
    org = uuid.uuid4()
    async with await _session() as session:
        await complete_meta_connection(
            session,
            cipher,
            app_id="a",
            app_secret="s",
            redirect_uri="r",
            code="c",
            organization_id=org,
            transport=httpx.MockTransport(handler),
        )
        repo = MetaConnectionRepository(session, cipher)
        assert await repo.load_token(org) == "LONG"  # 토큰은 저장됨
        row = await repo._get(org)
        assert row.ad_account_id is None  # best-effort라 None
        assert row.page_id is None
        assert row.scopes is None
