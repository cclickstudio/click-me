# 패널·페르소나 영속화 리포지토리 — panels·personas 테이블 CRUD (SQL은 여기에만)
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.simulation import models
from domain.simulation.contracts.schemas import Persona

# 페르소나 결정적 id 네임스페이스 — (panel_id, ref)로 고정해 런마다 동일 행을 가리킴(§3.6).
_NS = uuid.NAMESPACE_OID


class PanelRepository:
    """고정 패널 + 페르소나 영속화. service가 '저장 지휘', SQL은 여기서.

    §3.6 고정 패널 — panels.version 은 UNIQUE. 런마다 새로 만들지 않고, 같은 version 이 있으면
    그 패널·페르소나를 재사용한다(첫 런이 생성, 이후 런은 참조). 결정적 id + 조회-후-삽입으로
    PostgreSQL/SQLite 모두에서 idempotent.
    """

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
        """고정 패널 1건(version 재사용) + 페르소나 N건(없는 것만) 저장.

        반환: (panel_id, {persona_ref → persona_uuid}). UNIQUE(version) 충돌을 피하려
        같은 version 패널이 있으면 그 id 를 재사용하고 panel INSERT 를 건너뛴다.
        """
        existing = await self._s.scalar(select(models.Panel).where(models.Panel.version == version))
        if existing is not None:
            panel_id = existing.id  # 고정 패널 재사용
        else:
            panel_id = uuid.uuid5(_NS, f"panel:{version}")
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
            await self._s.flush()  # personas FK 충족을 위해 부모 먼저

        # (panel_id, ref) 결정적 id → 이미 있으면 참조만, 없으면 INSERT.
        id_map: dict[str, uuid.UUID] = {
            p.persona_id: uuid.uuid5(_NS, f"persona:{panel_id}:{p.persona_id}") for p in personas
        }
        present: set[uuid.UUID] = set()
        if id_map:
            rows = await self._s.execute(
                select(models.Persona.id).where(models.Persona.id.in_(list(id_map.values())))
            )
            present = {r[0] for r in rows}
        for p in personas:
            pid = id_map[p.persona_id]
            if pid in present:
                continue  # 고정 패널 멤버 재사용
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
                    socioeconomic=p.socioeconomic,
                    profile_narrative=p.profile_narrative,
                )
            )
        await self._s.flush()
        return panel_id, id_map

    async def get(self, panel_id: uuid.UUID) -> models.Panel | None:
        return await self._s.get(models.Panel, panel_id)
