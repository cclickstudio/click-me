# 시뮬레이터 소유 ORM 엔티티 — 추후 다른 도메인 ERD 확정 시 core/models.py로 병합
#
# 현재는 도메인 로컬 DeclarativeBase로 격리해 core 메타데이터 오염을 피한다.
# projects / ads 는 core/models.py 소유이므로 여기서 재정의하지 않고 UUID FK로만 참조.
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# JSONB(Postgres) / JSON(SQLite 테스트) — 동일 모델로 양쪽 동작. Uuid 는 PG=UUID·그 외=CHAR.
_JSONB = JSONB().with_variant(JSON(), "sqlite")


class SimBase(DeclarativeBase):
    """시뮬레이터 도메인 전용 Base (병합 전 격리용)."""


class Panel(SimBase):
    __tablename__ = "panels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    grounding_meta: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="BUILDING")
    built_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Persona(SimBase):
    __tablename__ = "personas"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    panel_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    ocean: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    media_behavior: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    consumption_values: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    profile_narrative: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdAnalysis(SimBase):
    __tablename__ = "ad_analyses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    ad_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    structured_analysis: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    detected_industry: Mapped[str | None] = mapped_column(String(100))
    detected_target: Mapped[str | None] = mapped_column(String(100))
    detected_message: Mapped[str | None] = mapped_column(Text)
    intent_mismatch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mismatch_detail: Mapped[dict | None] = mapped_column(_JSONB)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Simulation(SimBase):
    __tablename__ = "simulations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    ad_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    ad_analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    panel_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    target_filter: Mapped[dict | None] = mapped_column(_JSONB)
    target_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="AUTO")
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    qa_passed_count: Mapped[int | None] = mapped_column(Integer)
    low_sample_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="QUEUED")
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    error_detail: Mapped[dict | None] = mapped_column(_JSONB)
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PersonaReaction(SimBase):
    __tablename__ = "persona_reactions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    persona_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    exposure_context: Mapped[str | None] = mapped_column(String(50))
    aisas: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    drop_stage: Mapped[str | None] = mapped_column(String(20))
    drop_reason_tag: Mapped[str | None] = mapped_column(String(50))
    purchase_intent: Mapped[int] = mapped_column(Integer, nullable=False)
    trust: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rejection_reason_tag: Mapped[str | None] = mapped_column(String(50))
    emotion_tag: Mapped[str] = mapped_column(String(50), nullable=False)
    perceived_message: Mapped[str | None] = mapped_column(Text)
    perceived_target: Mapped[str | None] = mapped_column(String(100))
    utterance: Mapped[str | None] = mapped_column(Text)
    qa_passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    qa_fail_reason: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RubricScore(SimBase):
    __tablename__ = "rubric_scores"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    ad_analysis_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    dimension: Mapped[str] = mapped_column(String(50), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SimulationAggregate(SimBase):
    __tablename__ = "simulation_aggregates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    click_intent_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    ci_low: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    ci_high: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    purchase_intent: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    trust_avg: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)
    rejection_rate: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    variance_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload: Mapped[dict] = mapped_column(_JSONB, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
