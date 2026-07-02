# 🅰 Meta 연결 완료 오케스트레이션 — code→단기→장기 교환 + 자산 조회 후 암호화 저장 (멀티테넌트 (B))
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import MetaConnection
from domain.management.adapters.meta.client import MetaApiError, MetaClient
from domain.management.adapters.meta.connection_repository import MetaConnectionRepository
from domain.management.adapters.meta.oauth import (
    exchange_code_for_token,
    exchange_for_long_lived,
)
from domain.management.adapters.meta.token_crypto import TokenCipher


def _first_target(gran: dict[str, list], scopes: tuple[str, ...]) -> str | None:
    """granular_scopes에서 주어진 스코프들 중 첫 target_id를 반환."""
    for s in scopes:
        ids = gran.get(s) or []
        if ids:
            return str(ids[0])
    return None


async def _fetch_granted_assets(
    token: str,
    *,
    app_id: str | None,
    app_secret: str | None,
    api_version: str,
    transport: httpx.AsyncBaseTransport | None,
) -> dict[str, object]:
    """부여된 자산 ID(페이지·IG·광고계정)와 스코프를 조회한다(best-effort — 실패 시 None).

    비즈니스 로그인은 페이지·IG를 비즈니스로 부여해 /me/accounts엔 안 잡히므로,
    debug_token의 granular_scopes(스코프별 target_ids)가 선택 자산의 정답이다.
    ads가 특정 계정으로 안 묶이면(전체 부여) 추측하지 않고 None을 둔다 — 예전의
    '/me/adaccounts 첫 계정' 폴백은 의도치 않은 계정(옛 테스트 계정)에 바인딩되는
    사고를 냈다. 계정 미지정 시 처리는 호출자(fallback_ad_account_id)가 결정한다.
    """
    client = MetaClient(
        access_token=token,
        api_version=api_version,
        app_id=app_id,
        app_secret=app_secret,
        transport=transport,
    )
    out: dict[str, object] = {
        "ad_account_id": None,
        "page_id": None,
        "ig_user_id": None,
        "scopes": None,
    }
    try:
        dbg = await client.debug_token()
        out["scopes"] = dbg.get("scopes") or None
        gran = {g.get("scope"): (g.get("target_ids") or []) for g in dbg.get("granular_scopes", [])}
        out["page_id"] = _first_target(gran, ("pages_show_list", "pages_read_engagement"))
        out["ig_user_id"] = _first_target(gran, ("instagram_basic", "instagram_manage_insights"))
        ad = _first_target(gran, ("ads_management", "ads_read"))
        if ad:
            out["ad_account_id"] = ad if ad.startswith("act_") else f"act_{ad}"
    except MetaApiError:
        pass
    return out


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
    fallback_ad_account_id: str | None = None,
    api_version: str = "v21.0",
    transport: httpx.AsyncBaseTransport | None = None,
) -> MetaConnection:
    """콜백 code를 장기 토큰으로 교환하고 연결 자산을 조회해 org 연결로 암호화 저장한다(커밋 포함).

    계정 우선순위: 명시(ad_account_id) → 토큰 스코프에 묶인 계정 → fallback_ad_account_id
    (호출자가 주는 운영 기본 계정 — 임의 추측 금지). transport는 테스트용 MockTransport 주입 지점.
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
    assets = await _fetch_granted_assets(
        long_lived.access_token,
        app_id=app_id,
        app_secret=app_secret,
        api_version=api_version,
        transport=transport,
    )
    repo = MetaConnectionRepository(session, cipher)
    row = await repo.upsert(
        organization_id,
        access_token=long_lived.access_token,
        ad_account_id=ad_account_id or assets["ad_account_id"] or fallback_ad_account_id,
        page_id=assets["page_id"],
        ig_user_id=assets["ig_user_id"],
        scopes=assets["scopes"],
        token_expires_at=expires_at,
    )
    await session.commit()
    return row
