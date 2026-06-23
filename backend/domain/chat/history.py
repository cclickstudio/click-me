# 채팅 내역 영속화 — 프로젝트별 세션 생성·목록·메시지 조회·턴 저장(chat_sessions/chat_messages)
"""정규화 저장: 세션(chat_sessions) + 메시지(chat_messages). /complete가 매 턴 append_turn으로
사용자·어시스턴트 발화를 적재하고, 세션 제목·갱신 시각을 관리한다. 모든 함수는 best-effort —
세션이 없으면 조용히 무시(degrade)해 채팅 흐름을 막지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import AsyncSessionLocal
from core.models import ChatLongTermMemory, ChatMessage, ChatSession

_DEFAULT_TITLE = "새 채팅"


def _as_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    """문자열/UUID를 UUID로. 형식이 아니면 None(비DB session_id 등은 영속화 생략)."""
    if isinstance(value, uuid.UUID):
        return value
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError):
        return None


async def create_session(
    db: AsyncSession, project_id: str | None, title: str | None = None
) -> ChatSession:
    """새 채팅 세션 생성 — 프로젝트에 귀속(미선택이면 NULL)."""
    session = ChatSession(
        project_id=_as_uuid(project_id),
        title=(title or _DEFAULT_TITLE)[:200],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(db: AsyncSession, project_id: str | None) -> list[dict]:
    """프로젝트의 세션 목록 — 최근 갱신 순, 메시지 수 포함."""
    pid = _as_uuid(project_id)
    if pid is None:
        return []
    rows = await db.execute(
        select(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .where(ChatSession.project_id == pid)
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
    )
    return [
        {
            "id": str(s.id),
            "title": s.title,
            "project_id": str(s.project_id) if s.project_id else None,
            "message_count": count,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        }
        for s, count in rows.all()
    ]


async def get_messages(db: AsyncSession, session_id: str) -> list[dict]:
    """세션의 메시지 내역 — 시간 순. meta 포함."""
    sid = _as_uuid(session_id)
    if sid is None:
        return []
    rows = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == sid)
        .order_by(ChatMessage.created_at.asc())
    )
    return [{"role": m.role, "content": m.content, "meta": m.meta} for m in rows.scalars()]


async def append_turn(
    db: AsyncSession,
    session_id: str,
    user_content: str,
    assistant_content: str,
    meta: dict | None = None,
    user_meta: dict | None = None,
) -> None:
    """한 턴(사용자 발화 + 어시스턴트 답변)을 세션에 적재. 세션 없으면 무시(degrade).

    user_meta: 사용자 메시지에 붙일 메타(예: 첨부 이미지 URL {"image_url": ...}).
    """
    sid = _as_uuid(session_id)
    if sid is None:
        return
    session = await db.get(ChatSession, sid)
    if session is None:
        return
    db.add(ChatMessage(session_id=sid, role="user", content=user_content, meta=user_meta or None))
    db.add(
        ChatMessage(session_id=sid, role="assistant", content=assistant_content, meta=meta or None)
    )
    # 첫 사용자 발화로 제목 자동 설정(기본 제목일 때만).
    if session.title == _DEFAULT_TITLE and user_content.strip():
        session.title = user_content.strip()[:60]
    session.updated_at = datetime.now()
    await db.commit()


async def save_long_term_memory(
    project_id: str | None,
    memory_type: str,
    content: dict,
    user_id: str | None = None,
) -> None:
    """롱텀 메모리 1건 적재(best-effort) — 자체 세션. 오케스트레이터(비요청 스코프)에서 호출."""
    pid = _as_uuid(project_id)
    if pid is None:
        return  # 프로젝트 스코프 없으면 누적 의미 없음 — 생략
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                ChatLongTermMemory(
                    project_id=pid,
                    user_id=_as_uuid(user_id),
                    memory_type=memory_type,
                    content=content,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — 메모리 적재 실패가 채팅을 막지 않게
        print(f"[chat] long-term memory save error: {exc!r}")


async def get_long_term_memory(
    project_id: str | None, limit: int = 3, memory_type: str | None = None
) -> list[dict]:
    """프로젝트의 최근 롱텀 메모리 — 최신순. memory_type으로 필터(선택)."""
    pid = _as_uuid(project_id)
    if pid is None:
        return []
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(ChatLongTermMemory).where(ChatLongTermMemory.project_id == pid)
            if memory_type:
                stmt = stmt.where(ChatLongTermMemory.memory_type == memory_type)
            stmt = stmt.order_by(ChatLongTermMemory.created_at.desc()).limit(limit)
            rows = await db.execute(stmt)
            return [
                {
                    "memory_type": r.memory_type,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows.scalars()
            ]
    except Exception as exc:  # noqa: BLE001 — 조회 실패면 메모리 없이 진행
        print(f"[chat] long-term memory get error: {exc!r}")
        return []


async def delete_session(db: AsyncSession, session_id: str) -> bool:
    """세션 삭제 — 메시지는 FK CASCADE로 함께 삭제."""
    sid = _as_uuid(session_id)
    if sid is None:
        return False
    session = await db.get(ChatSession, sid)
    if session is None:
        return False
    await db.delete(session)
    await db.commit()
    return True
