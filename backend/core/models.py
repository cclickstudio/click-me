"""SQLAlchemy ORM models."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    desc,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

# ──────────────────────────────────────────────
# Auth
# ──────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    login_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # ADMIN | COMPANY | USER
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ACTIVE"
    )  # ACTIVE | PENDING
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # 관리자/기업이 발급한 계정 → 최초 로그인 시 비번 변경 유도
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
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
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")  # ACTIVE
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
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")  # ACTIVE
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
    team_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), nullable=True
    )  # 소속 팀(팀 단위 공유, 미배정이면 NULL)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), server_default="ACTIVE")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    organization: Mapped["Organization"] = relationship(back_populates="projects")
    ads: Mapped[list["Ad"]] = relationship(back_populates="project")


class Ad(Base):
    __tablename__ = "ads"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(20))  # image | text | video
    asset_url: Mapped[str | None] = mapped_column(String(500))
    copy_text: Mapped[str | None] = mapped_column(Text)
    industry_category: Mapped[str | None] = mapped_column(String(100))
    product_category: Mapped[str | None] = mapped_column(String(100))
    ad_objective: Mapped[str | None] = mapped_column(String(50))
    # 생성 출처 — '생성한 광고로 시뮬' 진입 시 그 generation을 느슨히 참조(cross-base라 FK 없음).
    # 채팅 개선모드가 이 값으로 상품 누끼(product_cutout) 키를 역추적해 재사용한다.
    generation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_filter: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), server_default="DRAFT")
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped["Project"] = relationship(back_populates="ads")


class ManagementKbDocument(Base):
    """매니지먼트 KB 문서(청크의 부모) — 테넌트·버전·출처·유효기간·상태 메타. 마이그 019."""

    __tablename__ = "management_kb_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # NULL=공통(global)
    visibility: Mapped[str] = mapped_column(String(16), default="global")
    source_type: Mapped[str] = mapped_column(
        String(32)
    )  # meta_official|internal_policy|benchmark|playbook
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(String(512))
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="ko")
    status: Mapped[str] = mapped_column(String(16), default="active")  # draft|active|deprecated
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # DB는 TIMESTAMPTZ — tz-aware datetime 인코딩 위해 timezone=True 필수.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    doc_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManagementKbChunk(Base):
    """매니지먼트 지식베이스 청크 (에이전틱 RAG) — 정책·플레이북·KPI 규칙의 벡터+키워드 검색."""

    __tablename__ = "management_kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128))  # 출처 파일명(인용용)
    title: Mapped[str] = mapped_column(String(256))  # 섹션 제목(인용용)
    chunk: Mapped[str] = mapped_column(Text)
    # OpenAI text-embedding-3-small 1536 = settings.embedding_dim(KB·LTM 동일). 변경 시 Alembic 마이그레이션 + kb_ingest 재실행 필요.
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # 마이그 019 — 문서 연결 + 메타(테넌트·버전·키워드검색). search_vector는 DB 생성열이라 미매핑.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("management_kb_documents.id", ondelete="CASCADE"), nullable=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunk_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ManagementChatSession(Base):
    """매니지먼트 어시스턴트 대화 세션 (멀티턴·관측). 마이그 019."""

    __tablename__ = "management_chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thread_id: Mapped[str] = mapped_column(String(128))
    campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ad_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ManagementChatMessage(Base):
    """대화 메시지 1건 (user|assistant|tool) + 모델·토큰·지연 관측. 마이그 019."""

    __tablename__ = "management_chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("management_chat_sessions.id", ondelete="CASCADE"), nullable=True
    )
    thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManagementAgentRun(Base):
    """에이전트 실행 1건 — 도구·검색·인용·HITL 상태. 마이그 019."""

    __tablename__ = "management_agent_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("management_chat_sessions.id", ondelete="CASCADE"), nullable=True
    )
    thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    tools_used: Mapped[list] = mapped_column(JSONB, default=list)
    retrieved_chunks: Mapped[list] = mapped_column(JSONB, default=list)
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    steps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    interrupt_state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    suggested_action: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManagementKbFeedback(Base):
    """어시스턴트 답변 피드백 (RAG 품질 개선 루프). 마이그 019."""

    __tablename__ = "management_kb_feedback"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    message_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)  # 1 like / -1 dislike
    failure_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    corrected_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ManagementKbEvalCase(Base):
    """RAG 평가 케이스 (대표 질문→기대 도구·근거). 마이그 019."""

    __tablename__ = "management_kb_eval_cases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question: Mapped[str] = mapped_column(Text)
    expected_tools: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_points: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expected_anomaly_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fixture_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimulationKbChunk(Base):
    """시뮬레이션 지식베이스 청크 (에이전틱 RAG) — KPI 정의·해석·방법론의 벡터 검색."""

    __tablename__ = "simulation_kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128))  # 출처 파일명(인용용)
    title: Mapped[str] = mapped_column(String(256))  # 섹션 제목(인용용)
    chunk: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class GeneratorKbChunk(Base):
    """광고 생성 지식베이스 청크 (에이전틱 RAG) — 카피 전략·원칙·톤의 벡터 검색."""

    __tablename__ = "generator_kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128))  # 출처 파일명(인용용)
    title: Mapped[str] = mapped_column(String(256))  # 섹션 제목(인용용)
    chunk: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ClioKbChunk(Base):
    """CLIO 지식베이스 청크 — 광고 일반 지식의 벡터 검색."""

    __tablename__ = "clio_kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str] = mapped_column(String(128))  # 출처 파일명(인용용)
    title: Mapped[str] = mapped_column(String(256))  # 섹션 제목(인용용)
    chunk: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSession(Base):
    """채팅 세션 — 프로젝트에 귀속된 대화 하나. 메시지는 ChatMessage로 정규화 저장."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(200), default="새 채팅")  # 세션 목록 표시용
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    # 마지막 열람 시각(N5) — 이후 추가된 메시지를 미확인 알림으로 집계. NULL이면 전부 미확인.
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChatMessage(Base):
    """채팅 메시지 — 세션에 귀속된 한 발화(user|assistant). meta에 출처·위젯·인용 보관."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(
        ENUM("user", "assistant", name="chat_role", create_type=False)
    )
    content: Mapped[str] = mapped_column(Text)
    # 컬럼명은 metadata지만 SQLAlchemy 예약어라 속성은 meta로 매핑.
    meta: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatSessionSummary(Base):
    """채팅 세션 요약(구 chat_long_term_memory, 마이그 0006 개명) — 숏텀 압축 컨텍스트.

    다음 대화에 컨텍스트로 주입(최근 N개 조회). memory_type:
    sim_input | gen_input | user_pref | session_summary.
    sim_input·gen_input 적재는 팀 조율 후 중단 예정 — 롱텀은 chat_execution_history로 일원화.
    """

    __tablename__ = "chat_session_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    memory_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[dict] = mapped_column(JSONB)
    # 시맨틱 검색용 임베딩(text-embedding-3-small). nullable — 임베딩 전/실패 행은 최신순 폴백.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # 최신순 조회(project_id 필터 + created_at DESC) 최적화 — 실 DB와 동일 구성.
    __table_args__ = (Index("ix_chat_session_summaries_project", "project_id", desc("created_at")),)


class ChatExecutionHistory(Base):
    """실행 히스토리(구 execution_history, 마이그 0006 개명) — 채팅 에이전트의 롱텀 메모리.

    시뮬/생성/매니지먼트 기능 수행 이력(시간·종류·데이터)을 프로젝트 단위 누적.
    summary를 tsvector로 색인해 BM25급 키워드 서치(ts_rank_cd)로 조회한다.
    feature_type: simulation | generation | management.
    """

    __tablename__ = "chat_execution_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # 기능 수행 시간(도연 지시). 조회는 이 시각 기준.
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    feature_type: Mapped[str] = mapped_column(String(20))  # simulation | generation | management
    action: Mapped[str] = mapped_column(String(64))  # run_simulation · create_campaign 등 세부
    summary: Mapped[str] = mapped_column(Text, default="")  # BM25 검색 대상 평문(제목·카피·타깃 등)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)  # 기타 관련 데이터(입력·결과 요약)
    # BM25급 키워드 서치용 tsvector(생성 컬럼). 한국어 stemmer 부재 → 'simple'(공백 토큰).
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple', coalesce(summary, ''))", persisted=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_chat_execution_history_search_tsv", "search_tsv", postgresql_using="gin"),
    )


class ChatBrandProfile(Base):
    """채팅 브랜드 프로파일 — 프로젝트마다 브랜드 톤·타겟·카테고리 기억(매번 입력 불필요).

    제너레이터 brand_profiles(client_id PK)와 충돌하지 않도록 별도 테이블. project_id UNIQUE.
    """

    __tablename__ = "chat_brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    brand_name: Mapped[str | None] = mapped_column(String(200))
    tone: Mapped[str | None] = mapped_column(String(100))  # "친근한", "전문적인" 등
    target_audience: Mapped[str | None] = mapped_column(String(200))  # "20-30대 여성"
    product_category: Mapped[str | None] = mapped_column(String(100))
    keywords: Mapped[list | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AdTemplate(Base):
    """광고 설정 템플릿 — 자주 쓰는 시뮬/생성 입력을 명명 저장해 재사용(T12)."""

    __tablename__ = "ad_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100))  # "여름 캠페인", "뷰티 기본"
    template_type: Mapped[str] = mapped_column(String(10))  # "sim" | "gen"
    content: Mapped[dict] = mapped_column(JSONB)  # 설정값(폼 초기값)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutomationRun(Base):
    """자동화(APScheduler 워커) 실행 결과 1건 — 3도메인 공용 운영/관측 저장소.

    사람 승인이 필요 없는 자동화(감지·진단·집계·동기화)의 결과를 프로젝트 단위로 남겨
    프론트가 조회한다(탭 안 열려도 서버가 해둔 걸 화면이 읽음). 롱텀 메모리
    (chat_execution_history=성공 수행만)와 목적이 다른 별개 저장소 — 여기엔 미발견·에러
    포함 모든 틱 결과가 남는다. domain으로 management/generation/simulation을 공용 관리.
    dedup_key로 미해결(resolved_at IS NULL) 알림을 1행으로 강제(중복 통지 방지).
    """

    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain: Mapped[str] = mapped_column(String(20))  # management | generation | simulation
    job_name: Mapped[str] = mapped_column(
        String(64)
    )  # anomaly_scan · budget_pace · weekly_report …
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="finding")  # ok|finding|error|skipped
    severity: Mapped[str | None] = mapped_column(String(16), nullable=True)  # info|warning|critical
    title: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    suggested_action: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # 승인 플로 딥링크
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)  # rule·meta·confidence 등
    dedup_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    actor: Mapped[str] = mapped_column(String(16), default="auto")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_automation_runs_domain_project", "domain", "project_id", desc("created_at")),
        # 미해결(resolved_at IS NULL) 알림은 dedup_key당 1행 — 매 틱 중복 통지 방지(부분 유니크).
        Index(
            "uq_automation_runs_dedup_open",
            "dedup_key",
            unique=True,
            postgresql_where=text("resolved_at IS NULL AND dedup_key IS NOT NULL"),
        ),
    )


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BrandKit(Base):
    """브랜드 키트 — 조직 단위로 색·로고·톤을 명명 저장(여러 개 보유·선택)."""

    __tablename__ = "brand_kits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    brand_color: Mapped[str | None] = mapped_column(String(20))
    brand_logo_key: Mapped[str | None] = mapped_column(String(512))
    tone_and_manner: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ──────────────────────────────────────────────
# 광고 매니지먼트 (🤝 공동, R&R §7) — contracts/schemas.py 계약과 1:1
# 컬럼 규칙: 타임스탬프=TIMESTAMPTZ / 금액=BIGINT KRW / 유연 페이로드=JSONB /
#           판정·조인 신호=일반 컬럼+인덱스 / enum=VARCHAR + 앱 레벨 검증.
# tenant_id = organization_id 느슨 참조(FK 없음, 멀티테넌트 정렬용).
# ──────────────────────────────────────────────
_TS = DateTime(timezone=True)


class AuditEventRow(Base):
    """append-only 감사 로그 (게이트 #7). UPDATE/DELETE 코드 경로 없음."""

    __tablename__ = "management_audit_events"

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


class IdempotencyKeyRow(Base):
    """멱등키 선점 — key UNIQUE(PK) + INSERT ON CONFLICT DO NOTHING (게이트 #1)."""

    __tablename__ = "management_idempotency_keys"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    approval_id: Mapped[str] = mapped_column(String(64), index=True)
    claimed: Mapped[bool] = mapped_column(Boolean, default=True)
    result: Mapped[dict | None] = mapped_column(JSONB)  # ActionResult JSON — replay용 (게이트 #1)
    created_at: Mapped[datetime] = mapped_column(_TS, server_default=func.now())


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

    __tablename__ = "management_meta_connections"

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

    __tablename__ = "management_campaign_kpi_overrides"

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

    __tablename__ = "management_created_campaigns"

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
    # 집행 전 시뮬 예측 연결용 — 이 캠페인이 어떤 시뮬 런(simulations.id)으로 집행됐는지(없으면 미연결).
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
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


# ──────────────────────────────────────────────
# Management — 운영 알림 (이상 감지 C안, 스펙 2026-07-03)
# ──────────────────────────────────────────────


class ManagementNotification(Base):
    """운영 알림 — 이상 감지 consult 결과를 채팅과 분리 저장. kind는 도메인 프리픽스."""

    __tablename__ = "management_notifications"
    __table_args__ = (
        # 미해결 알림은 (org, kind, dedup_key)당 1행 — 멀티워커 dedup의 DB 백스톱.
        Index(
            "uq_mgmt_notif_open_dedup",
            "organization_id",
            "kind",
            "dedup_key",
            unique=True,
            postgresql_where=text("resolved_at IS NULL"),
            sqlite_where=text("resolved_at IS NULL"),
        ),
        Index("ix_mgmt_notif_org_recent", "organization_id", desc("last_notified_at")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # remediation만 필수
    kind: Mapped[str] = mapped_column(
        String(60), nullable=False
    )  # "management.remediation_consult"
    dedup_key: Mapped[str] = mapped_column(
        String(200), nullable=False
    )  # f"{campaign_id}:{anomaly}"
    payload: Mapped[dict] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False, default=dict
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # ignored|actioned|auto_normal
    consult_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    last_notified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    followup_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
