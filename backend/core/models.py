"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # ADMIN | COMPANY | USER
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE"
    )  # ACTIVE | PENDING
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # 관리자/기업이 발급한 계정 → 최초 로그인 시 비번 변경 유도
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id"), nullable=True
    )  # 소속 팀(USER만, 미배정이면 NULL)
    phone_num: Mapped[str | None] = mapped_column(String(30), nullable=True)
    user_email: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # 연락용(로그인 아님)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ──────────────────────────────────────────────
# Organization (기존 — slug/status 컬럼 추가)
# ──────────────────────────────────────────────


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    plan: Mapped[str] = mapped_column(
        String(50), default="free"
    )  # free | professional | enterprise
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # ACTIVE | PENDING
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    ads: Mapped[list["Ad"]] = relationship(back_populates="project")


class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(255))
    ad_type: Mapped[str] = mapped_column(String(50))  # image | text | video
    s3_key: Mapped[str | None] = mapped_column(String(512))
    analysis: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="ads")
    simulations: Mapped[list["SimulationResult"]] = relationship(back_populates="ad")


class SimulationResult(Base):
    __tablename__ = "simulation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id"))
    persona_count: Mapped[int] = mapped_column(Integer)
    distribution: Mapped[dict] = mapped_column(JSONB)  # 구매의향 분포 데이터
    personas: Mapped[dict] = mapped_column(JSONB)  # 페르소나 배열
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    ad: Mapped["Ad"] = relationship(back_populates="simulations")


class AdEmbedding(Base):
    """광고 벡터 임베딩 (RAG / A·B 비교용)."""

    __tablename__ = "ad_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ad_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ads.id"))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    messages: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Inquiry(Base):
    __tablename__ = "inquiries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdGeneration(Base):
    """광고 생성 요청 단위 — 생성모드 파이프라인 1회 실행."""

    __tablename__ = "ad_generations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending | running | completed | failed
    input: Mapped[dict] = mapped_column(JSONB)  # GenerationCreateRequest 원본
    product_analysis: Mapped[dict | None] = mapped_column(JSONB)  # 핵심가치/PainPoint/Benefit
    strategies: Mapped[list | None] = mapped_column(JSONB)  # 전략 3종
    selected_candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    candidates: Mapped[list["AdGenerationCandidate"]] = relationship(back_populates="generation")


class AdGenerationCandidate(Base):
    """생성된 광고 후보 — 생성 1회당 3종."""

    __tablename__ = "ad_generation_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ad_generations.id", ondelete="CASCADE")
    )
    idx: Mapped[int] = mapped_column(SmallInteger)  # 0 | 1 | 2
    strategy: Mapped[dict | None] = mapped_column(JSONB)  # {strategy_type, ...}
    template_id: Mapped[str | None] = mapped_column(String(10))  # A | B | C
    copy: Mapped[dict | None] = mapped_column(JSONB)  # {headline, body, cta}
    image_prompt: Mapped[str | None] = mapped_column(Text)
    s3_key: Mapped[str | None] = mapped_column(String(512))
    qa_result: Mapped[dict | None] = mapped_column(JSONB)  # QA Harness 7항목 결과
    qa_passed: Mapped[bool | None] = mapped_column(Boolean)
    explanation: Mapped[dict | None] = mapped_column(JSONB)  # 적용 타겟/전략/템플릿/근거
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    generation: Mapped["AdGeneration"] = relationship(back_populates="candidates")


class AdCampaignLog(Base):
    """Meta Marketing API 광고 집행 이력."""

    __tablename__ = "ad_campaign_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ad_generations.id", ondelete="SET NULL"), nullable=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ad_generation_candidates.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20))  # created | failed | mocked
    mocked: Mapped[bool] = mapped_column(Boolean, default=False)
    campaign_id: Mapped[str | None] = mapped_column(String(100))
    adset_id: Mapped[str | None] = mapped_column(String(100))
    creative_id: Mapped[str | None] = mapped_column(String(100))
    ad_id: Mapped[str | None] = mapped_column(String(100))
    budget: Mapped[int | None] = mapped_column(Integer)
    objective: Mapped[str | None] = mapped_column(String(50))
    targeting: Mapped[dict | None] = mapped_column(JSONB)
    request_payload: Mapped[dict | None] = mapped_column(JSONB)
    response_payload: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AdPublishLog(Base):
    """광고 플랫폼 게시 이력 — 요청/응답/오류 전체 기록."""

    __tablename__ = "ad_publish_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    generation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ad_generations.id", ondelete="SET NULL"), nullable=True
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ad_generation_candidates.id", ondelete="SET NULL"), nullable=True
    )
    platform: Mapped[str] = mapped_column(String(20), default="instagram")
    status: Mapped[str] = mapped_column(String(20))  # published | failed | mocked
    ig_container_id: Mapped[str | None] = mapped_column(String(100))
    ig_media_id: Mapped[str | None] = mapped_column(String(100))
    caption: Mapped[str | None] = mapped_column(Text)
    request_payload: Mapped[dict | None] = mapped_column(JSONB)
    response_payload: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# ──────────────────────────────────────────────
# 광고 매니지먼트 (🤝 공동, R&R §7) — contracts/schemas.py 계약과 1:1
# 컬럼 규칙: 타임스탬프=TIMESTAMPTZ / 금액=BIGINT KRW / 유연 페이로드=JSONB /
#           판정·조인 신호=일반 컬럼+인덱스 / enum=VARCHAR + 앱 레벨 검증.
# tenant_id = organization_id 느슨 참조(FK 없음, 멀티테넌트 정렬용).
# ──────────────────────────────────────────────
_TS = DateTime(timezone=True)


class ActionProposalRow(Base):
    """🅱 생산 제안 (ActionProposal 계약). 판정·조인 신호는 컬럼, 나머지는 payload."""

    __tablename__ = "action_proposals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    ad_account_id: Mapped[str] = mapped_column(String(64))
    action_type: Mapped[str] = mapped_column(String(48))
    action_tier: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), index=True)
    budget_before_krw: Mapped[int] = mapped_column(BigInteger)
    budget_after_krw: Mapped[int] = mapped_column(BigInteger)
    max_total_spend_krw: Mapped[int] = mapped_column(BigInteger)
    expected_state_version: Mapped[str] = mapped_column(String(48))
    proposal_hash: Mapped[str] = mapped_column(String(64))
    approval_policy_version: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(_TS, index=True)
    # evidence_metrics · hypothesis · confidence · metrics_as_of · target_object_ids
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class ApprovalRow(Base):
    """🅰 승인 기록 (ApprovedAction 계약). 복합 UNIQUE = 중복승인 멱등 (R&R P2)."""

    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint("proposal_id", "approval_policy_version", name="uq_approval_idem"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    approval_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # 계약 PK
    proposal_id: Mapped[str] = mapped_column(String(64), index=True)
    proposal_hash: Mapped[str] = mapped_column(String(64))  # executor 재검증용
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    approver_id: Mapped[str] = mapped_column(String(64))  # 사용자 ID 또는 "AUTO"
    action_tier: Mapped[int] = mapped_column(Integer)
    approval_policy_version: Mapped[str] = mapped_column(String(16))
    expected_state_version: Mapped[str] = mapped_column(String(48))
    execution_mode: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(_TS)  # 승인 자체 만료 (제안 TTL보다 짧음)
    approved_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class AuditEventRow(Base):
    """append-only 감사 로그 (게이트 #7). UPDATE/DELETE 코드 경로 없음."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    proposal_id: Mapped[str] = mapped_column(String(64), index=True)
    approval_id: Mapped[str | None] = mapped_column(String(64))  # 승인 전 이벤트는 null
    stage: Mapped[str] = mapped_column(String(24))  # validate / execute / result
    outcome: Mapped[str] = mapped_column(String(48))
    detail: Mapped[dict] = mapped_column(JSONB)
    at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class ExecutionRunRow(Base):
    """🅱 실행 워크플로 상태 + 플랫폼 스냅샷(부분 실패 보존)."""

    __tablename__ = "execution_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    approval_id: Mapped[str] = mapped_column(String(64), index=True)
    proposal_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24))  # WorkflowStatus
    result_status: Mapped[str | None] = mapped_column(String(24))  # ResultStatus
    failure_reason: Mapped[str | None] = mapped_column(String(48))
    platform_snapshot: Mapped[dict] = mapped_column(JSONB)
    executed_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class IdempotencyKeyRow(Base):
    """멱등키 선점 — key UNIQUE(PK) + INSERT ON CONFLICT DO NOTHING (게이트 #1)."""

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(64), index=True)
    claimed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
