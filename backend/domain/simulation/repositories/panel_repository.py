# 패널·페르소나 영속화 리포지토리 — panels·personas 테이블 CRUD (SQL은 여기에만)
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
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
                    weight=p.weight,
                )
            )
        await self._s.flush()
        return panel_id, id_map

    async def get(self, panel_id: uuid.UUID) -> models.Panel | None:
        return await self._s.get(models.Panel, panel_id)

    async def list_personas(
        self,
        version: str,
        *,
        gender: str | None = None,
        age_min: int | None = None,
        age_max: int | None = None,
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Individual 모드 페르소나 지정 선택용 — 가벼운 미리보기 목록(SQL 필터·페이지네이션).

        get_by_version처럼 전 항목(OCEAN·미디어행동 등)을 안 실어 1000명 규모에서도 가볍다.
        반환: (미리보기 목록, 필터 적용 후 총원).
        """
        panel = await self._s.scalar(select(models.Panel).where(models.Panel.version == version))
        if panel is None:
            return [], 0
        conds = [models.Persona.panel_id == panel.id]
        if gender:
            conds.append(models.Persona.gender == gender)
        if age_min is not None:
            conds.append(models.Persona.age >= age_min)
        if age_max is not None:
            conds.append(models.Persona.age <= age_max)
        total = await self._s.scalar(select(func.count()).select_from(models.Persona).where(*conds))
        rows = await self._s.scalars(
            select(models.Persona)
            .where(*conds)
            .order_by(models.Persona.id)
            .limit(limit)
            .offset(offset)
        )
        items = [
            {
                "persona_id": f"P_{row.id.hex[:8]}",
                "age": row.age,
                "gender": row.gender,
                "region": row.region,
                "narrative_snippet": (row.profile_narrative or "")[:80],
            }
            for row in rows
        ]
        return items, int(total or 0)

    async def get_by_version(self, version: str) -> tuple[uuid.UUID, list[Persona]] | None:
        """고정 패널을 version으로 조회 — 읽기 경로(§3.6). 없으면 None(호출측이 폴백 판단).

        DB에 없는 계약 필드(원본 persona_id 문자열·social_values_deep·social_economic)는
        DB에 저장하지 않는 결정 — persona_id는 DB id로 합성, 나머지는
        전 항목 빈 dict라 잃을 값이 없다(데이터 확보처 가이드.md 기준).
        """
        panel = await self._s.scalar(select(models.Panel).where(models.Panel.version == version))
        if panel is None:
            return None
        rows = await self._s.scalars(
            select(models.Persona).where(models.Persona.panel_id == panel.id)
        )
        personas = [
            Persona(
                persona_id=f"P_{row.id.hex[:8]}",
                age=row.age,
                gender=row.gender,
                region=row.region,
                ocean=row.ocean,
                media_behavior=row.media_behavior,
                consumption_values=row.consumption_values,
                socioeconomic=row.socioeconomic,
                weight=float(row.weight),
                profile_narrative=row.profile_narrative,
            )
            for row in rows
        ]
        return panel.id, personas
