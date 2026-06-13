# 시뮬레이션 실행 영속화 리포지토리 — simulations·ad_analyses·persona_reactions·rubric_scores·
# simulation_aggregates 한 트랜잭션 저장 (SQL은 여기에만)
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from domain.simulation import models
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
)


def _tag(value: Enum | str | None) -> str | None:
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else value


class SimulationRepository:
    """완료된 시뮬레이션 1회분(메타+반응+루브릭+집계)을 저장. 분석팀은 이 행들을 읽는다."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def save_run(
        self,
        *,
        ad_id: uuid.UUID,
        organization_id: uuid.UUID,
        panel_id: uuid.UUID,
        target_filter: dict | None,
        target_mode: str,
        sample_size: int,
        ad: AdInterpretation,
        reactions: list[PersonaReaction],
        rubric: list[RubricScore],
        aggregate: SimulationAggregate,
        persona_uuid_by_ref: dict[str, uuid.UUID],
    ) -> uuid.UUID:
        ana_id = uuid.uuid4()
        self._s.add(
            models.AdAnalysis(
                id=ana_id,
                ad_id=ad_id,
                structured_analysis=ad.structured_analysis,
                detected_industry=ad.detected_industry,
                detected_target=ad.detected_target,
                detected_message=ad.detected_message,
                intent_mismatch=ad.intent_mismatch,
                mismatch_detail=ad.mismatch_detail,
                model_version=ad.model_version,
            )
        )

        sim_id = uuid.uuid4()
        self._s.add(
            models.Simulation(
                id=sim_id,
                ad_id=ad_id,
                ad_analysis_id=ana_id,
                panel_id=panel_id,
                organization_id=organization_id,
                target_filter=target_filter,
                target_mode=target_mode,
                sample_size=sample_size,
                qa_passed_count=sum(1 for r in reactions if r.qa_passed),
                status="COMPLETED",
                model_version=ad.model_version,
                completed_at=datetime.now(),
            )
        )

        for r in reactions:
            self._s.add(
                models.PersonaReaction(
                    simulation_id=sim_id,
                    persona_id=persona_uuid_by_ref[r.persona_id],
                    exposure_context=r.exposure_context,
                    aisas=r.aisas.model_dump(),
                    drop_stage=r.drop_stage,
                    drop_reason_tag=_tag(r.drop_reason_tag),
                    purchase_intent=r.purchase_intent,
                    trust=r.trust,
                    rejected=r.rejected,
                    rejection_reason_tag=_tag(r.rejection_reason_tag),
                    emotion_tag=_tag(r.emotion_tag),
                    perceived_message=r.perceived_message,
                    perceived_target=r.perceived_target,
                    utterance=r.utterance,
                    qa_passed=r.qa_passed,
                    qa_fail_reason=r.qa_fail_reason,
                )
            )

        for s in rubric:
            self._s.add(
                models.RubricScore(
                    ad_analysis_id=ana_id,
                    dimension=s.dimension,
                    score=s.score,
                    evidence=s.evidence,
                )
            )

        self._s.add(
            models.SimulationAggregate(
                simulation_id=sim_id,
                click_intent_rate=aggregate.click_intent_rate,
                ci_low=aggregate.ci_low,
                ci_high=aggregate.ci_high,
                purchase_intent=aggregate.purchase_intent,
                trust_avg=aggregate.trust_avg,
                rejection_rate=aggregate.rejection_rate,
                variance_warning=aggregate.variance_warning,
                payload=aggregate.payload,
                engine_version=aggregate.engine_version,
            )
        )

        await self._s.flush()
        return sim_id

    async def get(self, simulation_id: uuid.UUID) -> models.Simulation | None:
        return await self._s.get(models.Simulation, simulation_id)
