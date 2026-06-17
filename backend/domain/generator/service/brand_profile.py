"""브랜드 프로필 — 로그인 없이 client_id(UUID)로 식별, DB 영속화.

서버 재시작 후에도 색·톤·로고키가 유지된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.db import AsyncSessionLocal
from core.models import BrandProfileRow


@dataclass
class BrandProfile:
    brand_color: str | None = None
    brand_logo_key: str | None = None
    tone_and_manner: str | None = None


async def get_profile(client_id: str) -> BrandProfile:
    async with AsyncSessionLocal() as session:
        row = await session.get(BrandProfileRow, client_id)
        if row is None:
            return BrandProfile()
        return BrandProfile(
            brand_color=row.brand_color,
            brand_logo_key=row.brand_logo_key,
            tone_and_manner=row.tone_and_manner,
        )


async def save_profile(
    client_id: str,
    *,
    brand_color: str | None = None,
    brand_logo_key: str | None = None,
    tone_and_manner: str | None = None,
) -> BrandProfile:
    """전달된 필드만 갱신(나머지 유지). 행이 없으면 생성."""
    async with AsyncSessionLocal() as session:
        row = await session.get(BrandProfileRow, client_id)
        if row is None:
            row = BrandProfileRow(client_id=client_id)
            session.add(row)
        if brand_color is not None:
            row.brand_color = brand_color
        if brand_logo_key is not None:
            row.brand_logo_key = brand_logo_key
        if tone_and_manner is not None:
            row.tone_and_manner = tone_and_manner
        await session.commit()
        return BrandProfile(
            brand_color=row.brand_color,
            brand_logo_key=row.brand_logo_key,
            tone_and_manner=row.tone_and_manner,
        )
