# 🅰 Meta 연결 영속화 — org별 장기 토큰을 암호화 저장 / 복호화 로드 (멀티테넌트 (A))
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import MetaConnection
from domain.management.adapters.meta.credentials import MetaCredentials
from domain.management.adapters.meta.token_crypto import TokenCipher


class MetaConnectionRepository:
    """meta_connections 입출력. 토큰은 cipher로 암호화해 저장하고 로드 시 복호화한다.

    org당 1건(unique organization_id) — upsert는 있으면 갱신, 없으면 생성.
    """

    def __init__(self, session: AsyncSession, cipher: TokenCipher) -> None:
        self._session = session
        self._cipher = cipher

    async def upsert(
        self,
        organization_id: uuid.UUID,
        *,
        access_token: str,
        ad_account_id: str | None = None,
        page_id: str | None = None,
        ig_user_id: str | None = None,
        scopes: list[str] | None = None,
        token_expires_at: datetime | None = None,
    ) -> MetaConnection:
        row = await self._get(organization_id)
        enc = self._cipher.encrypt(access_token)
        if row is None:
            row = MetaConnection(organization_id=organization_id, access_token_enc=enc)
            self._session.add(row)
        else:
            row.access_token_enc = enc
        row.ad_account_id = ad_account_id
        row.page_id = page_id
        row.ig_user_id = ig_user_id
        row.scopes = scopes
        row.token_expires_at = token_expires_at
        row.status = "active"
        await self._session.flush()
        return row

    async def load_token(self, organization_id: uuid.UUID) -> str | None:
        """복호화된 액세스 토큰. 연결이 없으면 None."""
        row = await self._get(organization_id)
        return None if row is None else self._cipher.decrypt(row.access_token_enc)

    async def load_credentials(
        self, organization_id: uuid.UUID, settings: object
    ) -> MetaCredentials | None:
        """org 연결을 MetaCredentials로 — build_meta_client 드롭인용. 연결 없으면 None.

        app_id/app_secret/graph 버전은 우리 앱 자격(settings), 토큰·광고계정은 org 연결에서 채운다.
        """
        row = await self._get(organization_id)
        if row is None:
            return None
        return MetaCredentials(
            meta_access_token=self._cipher.decrypt(row.access_token_enc),
            meta_ad_account_id=row.ad_account_id,
            meta_graph_api_version=getattr(settings, "meta_graph_api_version", None),
            meta_app_id=getattr(settings, "meta_app_id", None),
            meta_app_secret=getattr(settings, "meta_app_secret", None),
        )

    async def _get(self, organization_id: uuid.UUID) -> MetaConnection | None:
        result = await self._session.execute(
            select(MetaConnection).where(MetaConnection.organization_id == organization_id)
        )
        return result.scalar_one_or_none()
