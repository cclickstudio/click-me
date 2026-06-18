# 완료된 시뮬레이션 1회분을 DB에 영속화하는 오케스트레이터 — 패널·실행을 한 트랜잭션으로 저장
#
# service가 '저장 지휘'만 하도록, 세션 열기 + Panel·Simulation 리포지토리 호출을 여기서 묶는다.
# (SQL 자체는 두 repository 안에만.) core.db 를 import 하지 않고 session_factory 를 주입받아
# .env 미설정(개발/테스트) 환경에서도 모듈 로드가 깨지지 않게 한다. 미주입 시 service는 영속화 생략.
from __future__ import annotations

import uuid

from sqlalchemy import text
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
        ad_uuid = _as_uuid(request.ad_id)
        async with self._session_factory() as session:
            # project의 organization_id 승계 — simulations.organization_id FK 충족.
            project_uuid = _as_uuid(request.project_id)
            org_row = (
                await session.execute(
                    text("SELECT organization_id FROM projects WHERE id = :pid"),
                    {"pid": project_uuid},
                )
            ).first()
            org_id = (
                org_row[0]
                if org_row
                else _as_uuid(request.organization_id, fallback=_ORG_FALLBACK)
            )
            # ads 행 보장 — ad_analyses의 FK(ads.id) 충족. 없으면 현재 프로젝트에 광고 행 생성.
            # 실 DB 스키마(media_type·status…)에 맞춰 raw SQL로 INSERT(core.models.Ad와 불일치).
            ad_exists = (
                await session.execute(text("SELECT 1 FROM ads WHERE id = :id"), {"id": ad_uuid})
            ).first()
            if ad_exists is None:
                await session.execute(
                    text(
                        "INSERT INTO ads (id, project_id, title, media_type, "
                        "asset_url, copy_text, product_category, ad_objective) "
                        "VALUES (:id, :pid, :title, :mtype, :asset, :copy, :pcat, :obj)"
                    ),
                    {
                        "id": ad_uuid,
                        "pid": project_uuid,
                        "title": (request.ad_title or "(제목 없음)")[:255],
                        "mtype": "image" if request.ad_image_url else "text",
                        "asset": request.ad_image_url,
                        "copy": request.ad_content,
                        "pcat": request.product_category,
                        "obj": request.ad_objective,
                    },
                )
                await session.flush()  # ads → ad_analyses 참조
            panel_id, id_map = await PanelRepository(session).create(
                version=panel_version,
                seed=panel_seed,
                size=len(personas),
                model_version=ad.model_version,
                grounding_meta=grounding_meta or {"panel_version": panel_version},
                personas=personas,
            )
            sim_id = await SimulationRepository(session).save_run(
                ad_id=ad_uuid,
                organization_id=org_id,
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
