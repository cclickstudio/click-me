# 브랜드 키트 CRUD — 조직 단위로 색·로고·톤을 명명 저장(여러 개 보유·선택)
from __future__ import annotations

import uuid

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import BrandKit


def _to_dict(k: BrandKit) -> dict:
    return {
        "id": str(k.id),
        "name": k.name,
        "brand_color": k.brand_color,
        "brand_logo_key": k.brand_logo_key,
        "tone_and_manner": k.tone_and_manner,
        "created_at": k.created_at.isoformat(),
    }


async def list_kits(org_id: str) -> list[dict]:
    """조직의 브랜드 키트 목록(최신순)."""
    try:
        oid = uuid.UUID(org_id)
    except ValueError:
        return []
    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(BrandKit)
                    .where(BrandKit.organization_id == oid)
                    .order_by(BrandKit.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    return [_to_dict(k) for k in rows]


async def create_kit(
    org_id: str,
    created_by: uuid.UUID | None,
    *,
    name: str,
    brand_color: str | None = None,
    brand_logo_key: str | None = None,
    tone_and_manner: str | None = None,
) -> dict:
    async with AsyncSessionLocal() as session:
        kit = BrandKit(
            organization_id=uuid.UUID(org_id),
            created_by=created_by,
            name=name,
            brand_color=brand_color,
            brand_logo_key=brand_logo_key,
            tone_and_manner=tone_and_manner,
        )
        session.add(kit)
        await session.commit()
        await session.refresh(kit)
        return _to_dict(kit)


async def update_kit(
    org_id: str,
    kit_id: str,
    *,
    name: str,
    brand_color: str | None,
    brand_logo_key: str | None,
    tone_and_manner: str | None,
) -> dict | None:
    """키트 전체 갱신(조직 소유 검증). 없거나 타 조직이면 None."""
    try:
        oid, kid = uuid.UUID(org_id), uuid.UUID(kit_id)
    except ValueError:
        return None
    async with AsyncSessionLocal() as session:
        kit = await session.get(BrandKit, kid)
        if kit is None or kit.organization_id != oid:
            return None
        kit.name = name
        kit.brand_color = brand_color
        kit.brand_logo_key = brand_logo_key
        kit.tone_and_manner = tone_and_manner
        await session.commit()
        await session.refresh(kit)
        return _to_dict(kit)


async def delete_kit(org_id: str, kit_id: str) -> bool:
    """키트 삭제(조직 소유 검증)."""
    try:
        oid, kid = uuid.UUID(org_id), uuid.UUID(kit_id)
    except ValueError:
        return False
    async with AsyncSessionLocal() as session:
        kit = await session.get(BrandKit, kid)
        if kit is None or kit.organization_id != oid:
            return False
        await session.delete(kit)
        await session.commit()
        return True
