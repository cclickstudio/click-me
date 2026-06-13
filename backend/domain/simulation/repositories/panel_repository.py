# 패널·페르소나 영속화 리포지토리 — panels·personas 테이블 CRUD (SQL은 여기에만)
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from domain.simulation import models
from domain.simulation.contracts.schemas import Persona


class PanelRepository:
    """고정 패널 + 페르소나 영속화. service가 '저장 지휘', SQL은 여기서."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(
        self,
        *,
        version: str,
        seed: int,
        size: int,
        model_version: str,
        grounding_meta: dict,
        personas: list[Persona],
    ) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
        """패널 1건 + 페르소나 N건 저장. 반환: (panel_id, {persona_ref → persona_uuid})."""
        panel_id = uuid.uuid4()
        self._s.add(
            models.Panel(
                id=panel_id,
                version=version,
                size=size,
                seed=str(seed),
                model_version=model_version,
                grounding_meta=grounding_meta,
                status="READY",
                built_at=datetime.now(),
            )
        )
        id_map: dict[str, uuid.UUID] = {}
        for p in personas:
            pid = uuid.uuid4()
            id_map[p.persona_id] = pid
            self._s.add(
                models.Persona(
                    id=pid,
                    panel_id=panel_id,
                    age=p.age,
                    gender=p.gender,
                    region=p.region,
                    ocean=p.ocean,
                    media_behavior=p.media_behavior,
                    consumption_values=p.consumption_values,
                    profile_narrative=p.profile_narrative,
                )
            )
        await self._s.flush()
        return panel_id, id_map

    async def get(self, panel_id: uuid.UUID) -> models.Panel | None:
        return await self._s.get(models.Panel, panel_id)
