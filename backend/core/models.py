"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
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
    default_landing_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
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


class ManagementKbChunk(Base):
    """매니지먼트 지식베이스 청크 (에이전틱 RAG) — 정책·플레이북·KPI 규칙의 벡터 검색."""

    __tablename__ = "management_kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128))  # 출처 파일명(인용용)
    title: Mapped[str] = mapped_column(String(256))  # 섹션 제목(인용용)
    chunk: Mapped[str] = mapped_column(Text)
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


class BrandProfileRow(Base):
    """제너레이터 브랜드 설정 — 로그인 없이 client_id(브라우저 UUID)로 식별·영속."""

    __tablename__ = "brand_profiles"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    brand_color: Mapped[str | None] = mapped_column(String(20))
    brand_logo_key: Mapped[str | None] = mapped_column(String(512))
    tone_and_manner: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


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
    event_id: Mapped[str | None] = mapped_column(String(64), index=True)  # AuditEvent.event_id
    category: Mapped[str | None] = mapped_column(String(64))  # 예: "executor.completed"
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    proposal_id: Mapped[str] = mapped_column(String(64), index=True)
    approval_id: Mapped[str | None] = mapped_column(String(64))  # 승인 전 이벤트는 null
    run_id: Mapped[str | None] = mapped_column(String(64))  # 실행 run 연결
    stage: Mapped[str | None] = mapped_column(String(24))  # 코드 미생성 — nullable
    outcome: Mapped[str | None] = mapped_column(String(48))  # 코드 미생성 — nullable
    detail: Mapped[dict] = mapped_column(JSONB)  # AuditEvent.payload (마스킹 후)
    at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())  # occurred_at


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
    result: Mapped[dict | None] = mapped_column(JSONB)  # ActionResult JSON — replay용 (게이트 #1)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


class RegenerationJobRow(Base):
    """🅱 채팅이 트리거한 재생성 비동기 job 상태(설계 2026-06-22). v1 in-process 전제."""

    __tablename__ = "regeneration_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    campaign_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    selection_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    candidates: Mapped[dict | None] = mapped_column(JSONB)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(64))
    proposal: Mapped[dict | None] = mapped_column(JSONB)
    outcome_reason: Mapped[str | None] = mapped_column(String(48))
    error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(_TS, index=True, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(_TS)
    finished_at: Mapped[datetime | None] = mapped_column(_TS)


class RemediationEscalationRow(Base):
    """🅱 시간축 에스컬레이션 사다리 진행 상태 — 캠페인당 active 1건 (re_evaluate 소유).

    파괴도 낮은 조치부터 우선순위대로 시도하고, 회복(원래 anomaly 소멸)이 안 되면 다음 단계로
    올린다. 회복 판정은 재탐지로만 하므로 baseline 스냅샷은 저장하지 않는다.
    """

    __tablename__ = "remediation_escalations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), index=True)
    ad_account_id: Mapped[str] = mapped_column(String(64))
    campaign_id: Mapped[str] = mapped_column(String(64), index=True)
    anomaly_type: Mapped[str] = mapped_column(String(48))  # 사다리를 연 anomaly = 회복 판정 기준
    ladder: Mapped[list] = mapped_column(JSONB)  # 우선순위 action_type 목록 스냅샷
    current_rung_index: Mapped[int] = mapped_column(Integer, default=0)
    rung_status: Mapped[str] = mapped_column(String(16))  # proposed | executed | rejected
    rung_executed_at: Mapped[datetime | None] = mapped_column(_TS)
    last_proposal_id: Mapped[str | None] = mapped_column(String(64))
    last_approval_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)  # active | recovered | exhausted
    opened_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())
    last_evaluated_at: Mapped[datetime | None] = mapped_column(_TS)
    updated_at: Mapped[datetime] = mapped_column(
        _TS, server_default=func.now(), onupdate=func.now()
    )


# ──────────────────────────────────────────────
# Persona Debate (시뮬레이터 4-1 페르소나 토론, simulations 1:N) — db-schema v3.1
# ──────────────────────────────────────────────


class PersonaDebate(Base):
    """페르소나 토론 세션(= 토론 아이디). simulations 1:N(UNIQUE 없음)."""

    __tablename__ = "persona_debates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # simulations 는 도메인 SimBase(별도 metadata)라 cross-base FK 선언 불가 — ORM 은 UUID 컬럼으로만
    # 참조(domain 의 FK 미선언 패턴과 동일). DB 레벨 FK·CASCADE 제약은 마이그레이션 007 이 보유.
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    topic: Mapped[str | None] = mapped_column(Text)
    rounds_run: Mapped[int | None] = mapped_column(Integer)  # 실제 돈 라운드(2~4)
    stop_reason: Mapped[str | None] = mapped_column(String(20))  # consensus | dissensus | max
    judge_model: Mapped[str | None] = mapped_column(String(50))
    engines: Mapped[list | None] = mapped_column(JSONB)  # ["haiku","gpt","gemini"]
    judge_log: Mapped[dict | None] = mapped_column(JSONB)  # 라운드별 Judge 중간 정리
    final: Mapped[dict | None] = mapped_column(JSONB)  # headline/consensus/dissent/ranked_actions
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    participants: Mapped[list["PersonaDebateParticipant"]] = relationship(
        back_populates="debate", cascade="all, delete-orphan"
    )
    utterances: Mapped[list["PersonaDebateUtterance"]] = relationship(
        back_populates="debate", cascade="all, delete-orphan"
    )


class PersonaDebateParticipant(Base):
    """토론 패널 1명(기본 6명). debate 1:N. persona_id는 더미 문자열·실 UUID 양쪽 수용."""

    __tablename__ = "persona_debate_participants"
    __table_args__ = (UniqueConstraint("debate_id", "persona_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persona_debates.id", ondelete="CASCADE"), nullable=False
    )
    persona_id: Mapped[str] = mapped_column(String(50), nullable=False)  # "P-00011"
    persona_name: Mapped[str | None] = mapped_column(String(50))
    persona_profile: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(String(20))  # 피벗/완주자/거부자/…
    engine: Mapped[str | None] = mapped_column(String(20))  # haiku/gpt/gemini

    debate: Mapped["PersonaDebate"] = relationship(back_populates="participants")


class PersonaDebateUtterance(Base):
    """토론 발언 로그(라운드×패널). debate 1:N, participant 참조."""

    __tablename__ = "persona_debate_utterances"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    debate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("persona_debates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("persona_debate_participants.id", ondelete="CASCADE"), nullable=True
    )
    round: Mapped[int] = mapped_column(Integer, nullable=False)  # 1~4
    phase: Mapped[str | None] = mapped_column(String(10))  # 발산/반박/검증
    stance: Mapped[str | None] = mapped_column(String(10))  # positive/neutral/negative
    text: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    lever: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    debate: Mapped["PersonaDebate"] = relationship(back_populates="utterances")


class MetaConnection(Base):
    """테넌트(Organization)별 Meta 연결 — OAuth 장기 토큰을 암호화 저장 (멀티테넌트 (A)).

    외부 광고주가 자기 Meta 자산을 연결하면 org당 1건 생성된다. access_token_enc는
    AES-256-GCM 암호문(평문 토큰 저장·로그 금지 — CLAUDE.md 보안 규칙). scopes는 부여 권한
    목록(JSONB, SQLite 테스트에선 JSON), token_expires_at은 장기토큰 만료(갱신 트리거용).
    """

    __tablename__ = "meta_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    ad_account_id: Mapped[str | None] = mapped_column(String(64))
    page_id: Mapped[str | None] = mapped_column(String(64))
    ig_user_id: Mapped[str | None] = mapped_column(String(64))
    scopes: Mapped[list | None] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active | needs_reconnect
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CampaignKpiOverride(Base):
    """조직별 캠페인 수동 KPI(추정 CVR·ROAS) — 전환 추적 전 고객이 직접 넣는 값 영속.

    실측이 아니라 고객 비즈니스 통계 기반 추정(스펙: CVR·ROAS 재정의 #2). org+campaign 유니크.
    cvr=전환율(%), roas=투자수익률(배수). 둘 다 NULL이면 행 삭제(실측으로 복귀).
    """

    __tablename__ = "campaign_kpi_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[str] = mapped_column(String(64), nullable=False)
    cvr: Mapped[float | None] = mapped_column(Float)  # 전환율 % (수동 추정)
    roas: Mapped[float | None] = mapped_column(Float)  # 투자수익률 배수 (수동 추정)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("organization_id", "campaign_id", name="uq_kpi_override_org_campaign"),
    )


class CreatedCampaign(Base):
    """앱에서 생성한 캠페인 누적 기록 — 무엇을 언제 어떤 설정으로 만들었는지 영속.

    대시보드는 Meta에서 실시간 조회하지만, 이 표는 "우리가 만든 것"의 이력(삭제돼도 남음).
    tenant_id는 FK 없이 문자열(데모 테넌트도 수용). meta_campaign_id는 LIVE 생성 시 채워진다.
    """

    __tablename__ = "created_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    meta_campaign_id: Mapped[str | None] = mapped_column(String(64))  # LIVE 생성 시 Meta id
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(String(20), nullable=False)  # traffic | leads
    ad_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    daily_budget_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failed
    execution_mode: Mapped[str] = mapped_column(String(20), nullable=False)  # live | validate_only…
    # 집행 전 시뮬 예측 연결용 — 이 캠페인이 어떤 광고(ad_id)로 만들어졌는지(없으면 미연결).
    creative_ad_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 소프트 삭제 — Meta에서 캠페인 삭제 시 행을 지우지 않고 시각만 찍는다(감사 이력 보존).
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ──────────────────────────────────────────────
# Billing (크레딧 충전·집행 차감 영속)
# ──────────────────────────────────────────────


class PaymentOrderRow(Base):
    """크레딧 충전 주문 — 서버가 기억하는 금액(FE 변조 대조)·승인 상태."""

    __tablename__ = "payment_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    amount_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ready|done|failed|canceled
    payment_key: Mapped[str | None] = mapped_column(String(128))
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    cancel_response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditLedgerRow(Base):
    """크레딧 원장 — append-only(수정·삭제 경로 없음). 잔액은 delta 합으로 산출.

    CHARGE는 양수, SPEND/REFUND는 음수. ref_id는 주문 id 또는 집행 참조(campaign 등).
    """

    __tablename__ = "credit_ledger"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    delta_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(16), nullable=False)  # charge|spend|refund
    ref_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
