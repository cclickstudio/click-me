# 🅰 Meta 연결 완료 오케스트레이션 — code→단기→장기 토큰 교환 후 암호화 저장 (멀티테넌트 (B))
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import MetaConnection
from domain.management.adapters.meta.connection_repository import MetaConnectionRepository
from domain.management.adapters.meta.oauth import (
    exchange_code_for_token,
    exchange_for_long_lived,
)
from domain.management.adapters.meta.token_crypto import TokenCipher


async def complete_meta_connection(
    session: AsyncSession,
    cipher: TokenCipher,
    *,
    app_id: str,
    app_secret: str,
    redirect_uri: str,
    code: str,
    organization_id: uuid.UUID,
    ad_account_id: str | None = None,
    api_version: str = "v23.0",
    transport: httpx.AsyncBaseTransport | None = None,
) -> MetaConnection:
    """콜백 code를 장기 토큰으로 교환해 org 연결로 암호화 저장한다(커밋 포함).

    transport는 테스트용 MockTransport 주입 지점(실서비스는 None=실호출).
    """
    short = await exchange_code_for_token(
        app_id=app_id,
        app_secret=app_secret,
        redirect_uri=redirect_uri,
        code=code,
        transport=transport,
        api_version=api_version,
    )
    long_lived = await exchange_for_long_lived(
        app_id=app_id,
        app_secret=app_secret,
        short_lived_token=short.access_token,
        transport=transport,
        api_version=api_version,
    )
    expires_at = (
        datetime.now(UTC) + timedelta(seconds=long_lived.expires_in)
        if long_lived.expires_in
        else None
    )
    repo = MetaConnectionRepository(session, cipher)
    row = await repo.upsert(
        organization_id,
        access_token=long_lived.access_token,
        ad_account_id=ad_account_id,
        token_expires_at=expires_at,
    )
    await session.commit()
    return row
