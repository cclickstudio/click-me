# 시뮬레이션 실행 영속화 리포지토리 — simulations·ad_analyses·persona_reactions·rubric_scores·
# simulation_aggregates 한 트랜잭션 저장 (SQL은 여기에만)
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from domain.simulation import models
from domain.simulation.adapters.ad_image_store import proxy_url_for
from domain.simulation.contracts.schemas import (
    AdInterpretation,
    Aisas,
    Persona,
    PersonaReaction,
    RubricScore,
    SimulationAggregate,
)
from domain.simulation.tools.aggregation.ocean_segments import ocean_segment_breakdown
from domain.simulation.tools.objective_fit import assess_objective_fit


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
        simulation_id: uuid.UUID | None = None,
        created_by: uuid.UUID | None = None,
    ) -> uuid.UUID:
        ana_id = uuid.uuid4()
        self._s.add(
            models.AdAnalysis(
                id=ana_id,
                ad_id=ad_id,
                structured_analysis=ad.structured_analysis,
                detected_industry=ad.detected_industry,
                detected_objective=ad.detected_objective,
                detected_target=ad.detected_target,
                detected_message=ad.detected_message,
                intent_mismatch=ad.intent_mismatch,
                mismatch_detail=ad.mismatch_detail,
                model_version=ad.model_version,
            )
        )
        # 실 DB는 FK 강제(ORM은 FK 미선언) — 부모를 자식보다 먼저 flush해 INSERT 순서 보장.
        await self._s.flush()  # ad_analyses → simulations 참조

        sim_id = simulation_id or uuid.uuid4()  # 주입되면 run_id와 PK 통일(챗 즉시 조회)
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
                created_by=created_by,
                completed_at=datetime.now(),
            )
        )
        await self._s.flush()  # simulations → persona_responses·simulation_aggregates 참조

        for r in reactions:
            self._s.add(
                models.PersonaReaction(
                    simulation_id=sim_id,
                    persona_id=persona_uuid_by_ref[r.persona_id],
                    exposure_context=r.exposure_context,
                    weight=r.weight,
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
                    brand_recognized=r.brand_recognized,
                    perceived_brand=r.perceived_brand,
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
                brand_recognition_rate=aggregate.brand_recognition_rate,
                variance_warning=aggregate.variance_warning,
                effective_n=aggregate.effective_n,
                payload=aggregate.payload,
                engine_version=aggregate.engine_version,
            )
        )

        await self._s.flush()
        return sim_id

    async def get(self, simulation_id: uuid.UUID) -> models.Simulation | None:
        return await self._s.get(models.Simulation, simulation_id)

    async def get_full_result(self, simulation_id: uuid.UUID) -> dict | None:
        """simulation_id로 저장된 결과 전체를 SimRunResult 형태 dict로 재조립. 없으면 None.

        새로고침·프로젝트 패널 재진입 시 인메모리 런이 사라져도 DB에서 복원한다.
        objective_fit은 미저장이라 집계·반응으로 재계산한다.
        """
        sim = await self._s.get(models.Simulation, simulation_id)
        if sim is None:
            return None

        # 광고해석(1) — ad_analysis_id로 단건.
        ana = await self._s.get(models.AdAnalysis, sim.ad_analysis_id)

        # 페르소나(N) — panel_id로 조회. id(UUID)→persona_id(str)로 통일해 반응과 조인.
        persona_rows = (
            (
                await self._s.execute(
                    select(models.Persona).where(models.Persona.panel_id == sim.panel_id)
                )
            )
            .scalars()
            .all()
        )
        # 반응(N) — simulation_id로 조회. persona_id(UUID)→str로 통일.
        reaction_rows = (
            (
                await self._s.execute(
                    select(models.PersonaReaction).where(
                        models.PersonaReaction.simulation_id == simulation_id
                    )
                )
            )
            .scalars()
            .all()
        )
        # 루브릭(N) — ad_analysis_id로 조회.
        rubric_rows = (
            (
                await self._s.execute(
                    select(models.RubricScore).where(
                        models.RubricScore.ad_analysis_id == sim.ad_analysis_id
                    )
                )
            )
            .scalars()
            .all()
        )
        # 집계(1) — simulation_id로 단건.
        aggregate_row = (
            await self._s.execute(
                select(models.SimulationAggregate).where(
                    models.SimulationAggregate.simulation_id == simulation_id
                )
            )
        ).scalar_one_or_none()

        # DB row → contracts 스키마 복원 → model_dump.
        ad_obj = (
            AdInterpretation(
                ad_id=str(ana.ad_id),
                structured_analysis=ana.structured_analysis or {},
                detected_industry=ana.detected_industry,
                detected_objective=ana.detected_objective,
                detected_target=ana.detected_target,
                detected_message=ana.detected_message,
                intent_mismatch=ana.intent_mismatch,
                mismatch_detail=ana.mismatch_detail,
                model_version=ana.model_version,
            )
            if ana is not None
            else None
        )

        persona_objs = [
            Persona(
                persona_id=str(p.id),
                age=p.age,
                gender=p.gender,
                region=p.region,
                ocean=p.ocean or {},
                media_behavior=p.media_behavior or {},
                consumption_values=p.consumption_values or {},
                socioeconomic=p.socioeconomic or {},
                profile_narrative=p.profile_narrative or "",
            )
            for p in persona_rows
        ]

        reaction_objs = [
            PersonaReaction(
                persona_id=str(r.persona_id),
                exposure_context=r.exposure_context,
                weight=float(r.weight),
                aisas=Aisas(**(r.aisas or {})),
                drop_stage=r.drop_stage,
                drop_reason_tag=r.drop_reason_tag,
                purchase_intent=r.purchase_intent,
                trust=r.trust,
                rejected=r.rejected,
                rejection_reason_tag=r.rejection_reason_tag,
                emotion_tag=r.emotion_tag,
                perceived_message=r.perceived_message,
                perceived_target=r.perceived_target,
                brand_recognized=r.brand_recognized,
                perceived_brand=r.perceived_brand,
                utterance=r.utterance,
                qa_passed=r.qa_passed,
                qa_fail_reason=r.qa_fail_reason,
            )
            for r in reaction_rows
        ]

        rubric_objs = [
            RubricScore(dimension=s.dimension, score=s.score, evidence=s.evidence or {})
            for s in rubric_rows
        ]

        aggregate_obj = (
            SimulationAggregate(
                click_intent_rate=float(aggregate_row.click_intent_rate),
                ci_low=float(aggregate_row.ci_low),
                ci_high=float(aggregate_row.ci_high),
                purchase_intent=float(aggregate_row.purchase_intent),
                trust_avg=float(aggregate_row.trust_avg),
                rejection_rate=float(aggregate_row.rejection_rate),
                brand_recognition_rate=float(aggregate_row.brand_recognition_rate),
                variance_warning=aggregate_row.variance_warning,
                effective_n=float(aggregate_row.effective_n),
                payload=aggregate_row.payload or {},
                engine_version=aggregate_row.engine_version,
            )
            if aggregate_row is not None
            else None
        )

        sid = str(simulation_id)
        result: dict = {
            "run_id": sid,  # 원본 run_id는 DB 미보유 → simulation_id로 대체.
            "simulation_id": sid,
            "ad_analysis": ad_obj.model_dump() if ad_obj is not None else None,
            "personas": [p.model_dump() for p in persona_objs],
            "reactions": [r.model_dump() for r in reaction_objs],
            "rubric_scores": [s.model_dump() for s in rubric_objs],
            "aggregate": aggregate_obj.model_dump() if aggregate_obj is not None else None,
            # OCEAN 성향별 반응 분해 — 미저장이라 페르소나·반응으로 재계산(상세 리포트 표시용).
            "ocean_segments": ocean_segment_breakdown(persona_objs, reaction_objs),
        }

        # 광고 메타 재조회 — ad_objective(objective_fit 재계산용) + asset_url(이미지 표시용).
        ad_row = (
            await self._s.execute(
                text("SELECT ad_objective, asset_url FROM ads WHERE id = :id"),
                {"id": sim.ad_id},
            )
        ).first()
        ad_objective = ad_row[0] if ad_row else None
        # 저장된 asset 참조(s3 key 또는 외부 URL)를 표시용 프록시 URL로 변환(자격증명 노출 방지).
        result["ad_asset_url"] = proxy_url_for(ad_row[1] if ad_row else None)

        # objective_fit 재계산 — ads.ad_objective + 집계/반응 신호로(미저장이라 재계산).
        if ad_objective and aggregate_obj is not None:
            fit = assess_objective_fit(ad_objective, aggregate_obj, reaction_objs)
            result["objective_fit"] = fit.model_dump() if fit is not None else None

        return result
