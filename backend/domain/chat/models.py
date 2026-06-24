# 챗 오케스트레이터 ORM — 단일 chat_* 스키마. core Base에 등록(FK는 projects/users 참조).
"""대화 영속(세션·메시지)·롱텀 메모리(임베딩 회상)·브랜드 프로필.

임베딩 차원은 settings.embedding_dim(기본 1024, BGE-M3)과 일치해야 한다(KB와 공유).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.config import settings
from core.db import Base

_DIM = settings.embedding_dim  # 1024 (BGE-M3) — Vector 차원·LTM 적재 차원과 동일해야 함


class ChatSession(Base):
    """대화 세션 — 정본. messages jsonb 제거(chat_messages 행으로 정규화)."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    # user_id·org_id: 인증 미연동이라 plain UUID(FK 없음). 026이 동형 추가.
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(String(200), server_default="새 채팅")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)  # 롤링 요약(토큰 윈도우 압축)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    """대화 메시지 — 정본. route로 어느 서브에이전트가 답했는지 태깅."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|system|tool (026이 enum→varchar)
    content: Mapped[str] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # general|management|simulation|generation
    meta: Mapped[dict] = mapped_column(
        "metadata", JSONB, default=dict
    )  # 컬럼명 metadata(예약어 회피 매핑)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatLongTermMemory(Base):
    """롱텀 메모리 — 세션 넘는 사실·선호·결정. 임베딩 top-k + 고salience always-load."""

    __tablename__ = "chat_long_term_memory"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    memory_type: Mapped[str] = mapped_column(String(32))  # fact | preference | decision ...
    content: Mapped[dict] = mapped_column(JSONB)
    # TODO(perf): pgvector hnsw 인덱스는 후속 마이그레이션에서 추가(빈 테이블).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(_DIM), nullable=True)
    salience: Mapped[float] = mapped_column(server_default="0.5")  # 0~1, 항상로드 임계 이상
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatBrandProfile(Base):
    """구조화 브랜드 프로필 — synthesize always-load 입력(project당 1행)."""

    __tablename__ = "chat_brand_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), unique=True, nullable=False
    )
    brand_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_audience: Mapped[str | None] = mapped_column(String(200), nullable=True)
    product_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    keywords: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
