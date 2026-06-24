# PgChatRepo — chat_sessions·chat_messages 영속(ChatRepo 포트 구현).
from __future__ import annotations

import uuid

from sqlalchemy import func, select, update

from core.db import AsyncSessionLocal
from domain.chat.contracts.schemas import MessageDTO, SessionDTO
from domain.chat.models import ChatMessage, ChatSession


class PgChatRepo:
    """세션·메시지 CRUD. 세션 팩토리 주입(테스트는 개인 DB 팩토리)."""

    def __init__(self, session_factory=AsyncSessionLocal) -> None:
        self._sf = session_factory

    async def create_session(
        self, *, session_id=None, project_id, user_id, organization_id, title="새 채팅"
    ) -> SessionDTO:
        row = ChatSession(
            id=session_id or uuid.uuid4(),
            project_id=project_id,
            user_id=user_id,
            organization_id=organization_id,
            title=title,
        )
        async with self._sf() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return self._to_session(row)

    async def get_session(self, session_id: uuid.UUID) -> SessionDTO | None:
        async with self._sf() as db:
            row = await db.get(ChatSession, session_id)
        return self._to_session(row) if row else None

    async def list_sessions(self, *, user_id, limit=20) -> list[SessionDTO]:
        stmt = select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit)
        if user_id is not None:
            stmt = stmt.where(ChatSession.user_id == user_id)
        async with self._sf() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [self._to_session(r) for r in rows]

    async def append_message(
        self, *, session_id, role, content, route=None, meta=None
    ) -> MessageDTO:
        row = ChatMessage(
            session_id=session_id, role=role, content=content, route=route, meta=meta or {}
        )
        async with self._sf() as db:
            db.add(row)
            await db.commit()
            await db.refresh(row)
        return self._to_message(row)

    async def get_messages(self, session_id: uuid.UUID, *, limit=100) -> list[MessageDTO]:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        async with self._sf() as db:
            rows = (await db.execute(stmt)).scalars().all()
        return [self._to_message(r) for r in rows]

    async def update_summary(self, session_id: uuid.UUID, summary: str) -> None:
        # updated_at 명시 갱신 — Core update()는 ORM onupdate를 발화하지 않음.
        async with self._sf() as db:
            await db.execute(
                update(ChatSession)
                .where(ChatSession.id == session_id)
                .values(summary=summary, updated_at=func.now())
            )
            await db.commit()

    @staticmethod
    def _to_session(r: ChatSession) -> SessionDTO:
        return SessionDTO(
            id=r.id,
            project_id=r.project_id,
            user_id=r.user_id,
            organization_id=r.organization_id,
            title=r.title,
            summary=r.summary,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )

    @staticmethod
    def _to_message(r: ChatMessage) -> MessageDTO:
        return MessageDTO(
            id=r.id,
            session_id=r.session_id,
            role=r.role,
            content=r.content,
            route=r.route,
            meta=r.meta or {},
            created_at=r.created_at,
        )
