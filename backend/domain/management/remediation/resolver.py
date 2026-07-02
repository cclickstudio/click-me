# 캠페인→프로젝트 역추적 — 오배정=기밀 노출이므로 결정론 체인 + org fail-closed (🅱)
"""스펙 §7. 체인 1: AdCampaignLog(campaign_id) → generation → project(+org).
- expected_org_id가 주어지면 불일치 시 None(fail-closed). 스케줄러 tenant="global"이면 미검증.
- 반환 (project_id, organization_id) — 해석된 org는 consult meta의 org_id 정본이 된다.
체인 2(생성 제안 링크)는 campaign_id↔proposal 연계 저장 확인 후 후속 — _CHAIN에 추가.
타 도메인 테이블 raw SQL 읽기는 SimPredictionReader 선례와 동일 성격(읽기 전용).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

# 주의: ad_generations.deleted_at은 실 DB에는 있으나 ORM(core/models.py)에는 없는
# 드리프트 컬럼(2026-07-02 information_schema 확인) — soft-delete 제외는 raw SQL이라 가능.
_VIA_CAMPAIGN_LOG = text(
    """
    SELECT g.project_id, p.organization_id
    FROM ad_campaign_logs l
    JOIN ad_generations g ON g.id = l.generation_id
    JOIN projects p ON p.id = g.project_id
    WHERE l.campaign_id = :cid
      AND g.project_id IS NOT NULL
      AND g.deleted_at IS NULL
      AND p.deleted_at IS NULL
    ORDER BY l.created_at DESC
    LIMIT 1
    """
)


async def _via_campaign_log(campaign_id: str, session_factory: Any) -> tuple[str, str] | None:
    async with session_factory() as db:
        row = (await db.execute(_VIA_CAMPAIGN_LOG, {"cid": campaign_id})).first()
        if row is None:
            return None
        return str(row[0]), str(row[1])


#: 순서 리스트 — 체인 2(생성 제안 링크)는 연계 확인 후 여기 추가한다.
_CHAIN = (_via_campaign_log,)


async def resolve_project(
    campaign_id: str, *, expected_org_id: str | None = None, session_factory: Any = None
) -> tuple[str, str] | None:
    """체인 순서대로 시도 → (project_id, org_id). org 불일치·전부 실패면 None(예외 안 나감)."""
    if session_factory is None:
        from core.db import AsyncSessionLocal  # noqa: PLC0415 — 테스트 주입 지원

        session_factory = AsyncSessionLocal
    for step in _CHAIN:
        try:
            resolved = await step(campaign_id, session_factory)
        except Exception:  # noqa: BLE001 — 역추적 실패는 다음 체인/skip
            continue
        if resolved is None:
            continue
        if expected_org_id is not None and resolved[1] != expected_org_id:
            return None  # fail-closed — 다른 org의 프로젝트로는 절대 배달하지 않는다
        return resolved
    return None
