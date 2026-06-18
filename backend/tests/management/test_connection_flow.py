# Meta 연결 완료 오케스트레이션 — code→단기→장기 교환 후 장기토큰 암호화 저장 (Mock+SQLite)
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


def _two_step_transport(calls: list) -> httpx.MockTransport:
    # 1) code 교환 → 단기, 2) fb_exchange_token → 장기
    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        calls.append(params)
        if params.get("grant_type") == "fb_exchange_token":
            return httpx.Response(
                200, json={"access_token": "LONG", "token_type": "bearer", "expires_in": 5184000}
            )
        return httpx.Response(
            200, json={"access_token": "SHORT", "token_type": "bearer", "expires_in": 3600}
        )

    return httpx.MockTransport(handler)


async def test_complete_stores_long_lived_token_encrypted():
    calls = []
    transport = _two_step_transport(calls)
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
            ad_account_id="act_5",
            transport=transport,
        )
        repo = MetaConnectionRepository(session, cipher)
        # 저장된 건 장기 토큰(LONG)이어야 — 단기(SHORT) 아님
        assert await repo.load_token(org) == "LONG"
        # 두 번 호출(code 교환 + 장기 교환), 단기 토큰이 장기 교환에 전달됨
        assert len(calls) == 2
        assert calls[1]["fb_exchange_token"] == "SHORT"
        # 평문 미저장
        row = await repo._get(org)
        assert "LONG" not in row.access_token_enc
        assert row.ad_account_id == "act_5"
        assert row.token_expires_at is not None
