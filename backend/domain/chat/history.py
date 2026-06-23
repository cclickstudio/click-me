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
from core.models import (
    AdTemplate,
    ChatBrandProfile,
    ChatLongTermMemory,
    ChatMessage,
    ChatSession,
)

_BRAND_FIELDS = ("brand_name", "tone", "target_audience", "product_category", "keywords")

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
    return [
        {"id": str(m.id), "role": m.role, "content": m.content, "meta": m.meta}
        for m in rows.scalars()
    ]


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
    # 10턴 초과 시 앞 대화를 요약·압축(best-effort, 모크/키 없으면 생략).
    await summarize_and_compress(str(sid), str(session.project_id) if session.project_id else None)


_SUMMARY_THRESHOLD_TURNS = 10  # 이 턴 수 초과 시 앞 대화를 요약·압축
_KEEP_RECENT_MSGS = 8  # 요약 후에도 원문 유지하는 최근 메시지 수(4턴)


async def summarize_and_compress(session_id: str, project_id: str | None) -> None:
    """대화가 10턴을 넘으면 앞부분을 LLM으로 요약해 session_summary 롱텀 메모리로 저장.

    best-effort — 키 없음/모크/실패 시 조용히 생략. 이미 같은 범위를 요약했으면 재요약 안 함.
    """
    from core.config import settings  # noqa: PLC0415 — 지연 임포트(설정 의존 최소화)

    key = getattr(settings, "openai_api_key", None)
    if getattr(settings, "use_mock", True) or not key:
        return
    try:
        async with AsyncSessionLocal() as db:
            rows = await get_messages(db, session_id)
    except Exception:  # noqa: BLE001
        return
    # 10턴(=20메시지) 이하면 요약 불필요.
    if len(rows) <= _SUMMARY_THRESHOLD_TURNS * 2:
        return
    older = rows[:-_KEEP_RECENT_MSGS]
    if not older:
        return
    # 같은 범위를 이미 요약했으면 스킵(중복 LLM 호출 방지).
    existing = await get_long_term_memory(project_id, limit=1, memory_type="session_summary")
    for e in existing:
        c = e.get("content") or {}
        if c.get("session_id") == session_id and (c.get("covered") or 0) >= len(older):
            return
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in older)
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(api_key=key)
        model = getattr(settings, "chat_summary_model", "gpt-4o-mini")
        resp = await client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "다음 대화를 3~5문장 한국어로 요약하라. 사용자의 의도·결정·"
                        "언급한 광고/시뮬/생성 맥락을 보존하라. 문장 끝에 콜론을 쓰지 말 것."
                    ),
                },
                {"role": "user", "content": transcript},
            ],
        )
        summary = (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001 — 요약 실패가 채팅을 막지 않게
        print(f"[chat] summarize error: {exc!r}")
        return
    if summary:
        await save_long_term_memory(
            project_id,
            "session_summary",
            {"session_id": session_id, "summary": summary, "covered": len(older)},
        )


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


async def get_brand_profile(project_id: str | None) -> dict | None:
    """프로젝트의 브랜드 프로파일 조회(없으면 None)."""
    pid = _as_uuid(project_id)
    if pid is None:
        return None
    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                select(ChatBrandProfile).where(ChatBrandProfile.project_id == pid)
            )
            bp = row.scalar_one_or_none()
            if bp is None:
                return None
            return {
                "brand_name": bp.brand_name,
                "tone": bp.tone,
                "target_audience": bp.target_audience,
                "product_category": bp.product_category,
                "keywords": bp.keywords,
            }
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] brand profile get error: {exc!r}")
        return None


async def upsert_brand_profile(project_id: str | None, fields: dict) -> None:
    """브랜드 프로파일 부분 업데이트(없으면 생성). 빈 값은 무시(기존 보존)."""
    pid = _as_uuid(project_id)
    if pid is None:
        return
    updates = {k: v for k, v in fields.items() if k in _BRAND_FIELDS and v}
    if not updates:
        return
    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                select(ChatBrandProfile).where(ChatBrandProfile.project_id == pid)
            )
            bp = row.scalar_one_or_none()
            if bp is None:
                bp = ChatBrandProfile(project_id=pid, **updates)
                db.add(bp)
            else:
                for k, v in updates.items():
                    setattr(bp, k, v)
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] brand profile upsert error: {exc!r}")


async def pin_message(message_id: str, pinned: bool) -> bool:
    """메시지 핀 토글(T19) — ChatMessage.meta.pinned 갱신. 성공 시 True."""
    mid = _as_uuid(message_id)
    if mid is None:
        return False
    try:
        async with AsyncSessionLocal() as db:
            msg = await db.get(ChatMessage, mid)
            if msg is None:
                return False
            meta = dict(msg.meta or {})
            meta["pinned"] = pinned
            msg.meta = meta
            await db.commit()
            return True
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] pin message error: {exc!r}")
        return False


async def save_template(
    project_id: str | None, name: str, template_type: str, content: dict
) -> dict | None:
    """광고 설정 템플릿 저장(T12). 같은 이름이 있으면 내용 갱신(upsert)."""
    pid = _as_uuid(project_id)
    if pid is None or not name:
        return None
    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                select(AdTemplate).where(AdTemplate.project_id == pid, AdTemplate.name == name)
            )
            tpl = row.scalar_one_or_none()
            if tpl is None:
                tpl = AdTemplate(
                    project_id=pid, name=name, template_type=template_type, content=content
                )
                db.add(tpl)
            else:
                tpl.template_type = template_type
                tpl.content = content
            await db.commit()
            return {"name": name, "template_type": template_type}
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] template save error: {exc!r}")
        return None


async def list_templates(project_id: str | None) -> list[dict]:
    """프로젝트 템플릿 목록(최신순)."""
    pid = _as_uuid(project_id)
    if pid is None:
        return []
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(AdTemplate)
                .where(AdTemplate.project_id == pid)
                .order_by(AdTemplate.created_at.desc())
            )
            return [
                {
                    "id": str(t.id),
                    "name": t.name,
                    "template_type": t.template_type,
                    "content": t.content,
                }
                for t in rows.scalars()
            ]
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] template list error: {exc!r}")
        return []


async def get_template_by_name(project_id: str | None, name: str) -> dict | None:
    """이름으로 템플릿 조회 — 부분일치(가장 최근). 없으면 None."""
    pid = _as_uuid(project_id)
    if pid is None or not name:
        return None
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(AdTemplate)
                .where(AdTemplate.project_id == pid, AdTemplate.name.ilike(f"%{name}%"))
                .order_by(AdTemplate.created_at.desc())
            )
            t = rows.scalars().first()
            if t is None:
                return None
            return {"name": t.name, "template_type": t.template_type, "content": t.content}
    except Exception as exc:  # noqa: BLE001
        print(f"[chat] template get error: {exc!r}")
        return None


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
