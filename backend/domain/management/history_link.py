# 실행 확정 → 롱텀 메모리 연결 — 캠페인→프로젝트 역추적 + executor 기록 콜백 빌더
"""management 액션은 tenant 스코프라 프로젝트가 없다. created_campaigns의
creative_ad_id → ads.project_id 경로로 역추적해 chat_execution_history(프로젝트 스코프)에
남긴다. 연결 불가(수동 연동 캠페인 등)면 기록 생략 — 알림·감사 로그는 별도로 남는다.
전부 best-effort — 실패가 실행 결과를 바꾸지 않는다.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import or_, select

from core.db import AsyncSessionLocal
from core.execution_log import record_execution
from core.models import Ad, CreatedCampaign

if TYPE_CHECKING:
    from domain.management.contracts.schemas import (
        ActionProposal,
        ActionResult,
        ApprovedAction,
    )

_ACTION_LABELS = {
    "PAUSE_CAMPAIGN": "일시중지",
    "ACTIVATE_CAMPAIGN": "게재 시작",
    "INCREASE_BUDGET": "예산 증액",
    "DECREASE_BUDGET": "예산 감액",
    "REPLACE_CREATIVE": "소재 교체",
    "CREATE_CAMPAIGN": "캠페인 생성",
    "EXPAND_AUDIENCE": "타깃 확장",
    "CHANGE_BID_STRATEGY": "입찰 전략 변경",
}


def _maybe_uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


async def resolve_project_id(campaign_ids: list[str] | tuple[str, ...]) -> str | None:
    """캠페인 id(Meta id 또는 자체 uuid) → creative_ad_id → ads.project_id (best-effort)."""
    ids = [c for c in (campaign_ids or []) if c]
    if not ids:
        return None
    uuids = [u for u in (_maybe_uuid(c) for c in ids) if u is not None]
    try:
        async with AsyncSessionLocal() as db:
            conds = [CreatedCampaign.meta_campaign_id.in_(ids)]
            if uuids:
                conds.append(CreatedCampaign.id.in_(uuids))
            rows = await db.execute(select(CreatedCampaign).where(or_(*conds)))
            for camp in rows.scalars():
                ad_id = _maybe_uuid(camp.creative_ad_id or "")
                if ad_id is None:
                    continue
                ad = await db.get(Ad, ad_id)
                if ad is not None:
                    return str(ad.project_id)
    except Exception as exc:  # noqa: BLE001 — 역추적 실패면 기록 생략
        print(f"[management] project resolve error: {exc!r}")
    return None


def build_history_recorder():
    """executor 성공 시 호출될 콜백 — 롱텀 메모리(chat_execution_history)에 실행 기록."""
    from domain.management.contracts.schemas import AUTO_APPROVER  # noqa: PLC0415

    async def record(
        action: ApprovedAction, proposal: ActionProposal, result: ActionResult
    ) -> None:
        project_id = await resolve_project_id(proposal.target_object_ids)
        if project_id is None:
            return
        actor = "auto" if action.approver_id == AUTO_APPROVER else "user"
        label = _ACTION_LABELS.get(proposal.action_type, proposal.action_type)
        targets = " ".join(proposal.target_object_ids)
        summary = f"매니지먼트 {label} 실행 캠페인 {targets} {proposal.hypothesis}".strip()[:500]
        await record_execution(
            project_id,
            "management",
            proposal.action_type.lower(),
            summary,
            payload={
                "actor": actor,
                "action_type": proposal.action_type,
                "target_object_ids": list(proposal.target_object_ids),
                "execution_mode": action.execution_mode.value,
                "status": result.status.value,
            },
        )

    return record
