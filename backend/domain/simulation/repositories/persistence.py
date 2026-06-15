# 완료된 시뮬레이션 1회분을 DB에 영속화하는 오케스트레이터 — 패널·실행을 한 트랜잭션으로 저장
#
# service가 '저장 지휘'만 하도록, 세션 열기 + Panel·Simulation 리포지토리 호출을 여기서 묶는다.
# (SQL 자체는 두 repository 안에만.) core.db 를 import 하지 않고 session_factory 를 주입받아
# .env 미설정(개발/테스트) 환경에서도 모듈 로드가 깨지지 않게 한다. 미주입 시 service는 영속화 생략.
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
    SimulationRunRequest,
)
from domain.simulation.repositories.panel_repository import PanelRepository
from domain.simulation.repositories.simulation_repository import SimulationRepository

_ORG_FALLBACK = "clickme-default-org"  # organization_id 미지정 시 결정적 UUID 시드


def _as_uuid(value: str | None, *, fallback: str = "") -> uuid.UUID:
    """계약 식별자(문자열)를 UUID로. 이미 UUID 형식이면 그대로, 아니면 결정적 uuid5."""
    raw = value or fallback
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(uuid.NAMESPACE_OID, raw or _ORG_FALLBACK)


class SimulationPersistence:
    """완료 런(패널+페르소나+실행 메타+반응+루브릭+집계)을 한 트랜잭션으로 저장한다."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save_completed_run(
        self,
        *,
        request: SimulationRunRequest,
        ad: AdInterpretation,
        personas: list[Persona],
        reactions: list[PersonaReaction],
        rubric: list[RubricScore],
        aggregate: SimulationAggregate,
        panel_version: str,
        panel_seed: int = 0,
        grounding_meta: dict | None = None,
    ) -> uuid.UUID:
        """반환: 저장된 simulation_id. 호출자는 결과 dict에 실어 분석팀 핸드오프에 사용."""
        target_mode = getattr(request.target_mode, "value", str(request.target_mode))
        async with self._session_factory() as session:
            panel_id, id_map = await PanelRepository(session).create(
                version=panel_version,
                seed=panel_seed,
                size=len(personas),
                model_version=ad.model_version,
                grounding_meta=grounding_meta or {"panel_version": panel_version},
                personas=personas,
            )
            sim_id = await SimulationRepository(session).save_run(
                ad_id=_as_uuid(request.ad_id),
                organization_id=_as_uuid(request.organization_id, fallback=_ORG_FALLBACK),
                panel_id=panel_id,
                target_filter=request.target_filter,
                target_mode=target_mode,
                sample_size=request.sample_size,
                ad=ad,
                reactions=reactions,
                rubric=rubric,
                aggregate=aggregate,
                persona_uuid_by_ref=id_map,
            )
            await session.commit()
            return sim_id
