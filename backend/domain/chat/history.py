# 채팅 내역 영속화 — 프로젝트별 세션 생성·목록·메시지 조회·턴 저장(chat_sessions/chat_messages)
"""정규화 저장: 세션(chat_sessions) + 메시지(chat_messages). /complete가 매 턴 append_turn으로
사용자·어시스턴트 발화를 적재하고, 세션 제목·갱신 시각을 관리한다. 모든 함수는 best-effort —
세션이 없으면 조용히 무시(degrade)해 채팅 흐름을 막지 않는다.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import AsyncSessionLocal
from core.models import (
    AdTemplate,
    ChatBrandProfile,
    ChatLongTermMemory,
    ChatMessage,
    ChatSession,
)
from domain.chat.kb_ingest import EMBEDDING_MODEL

_BRAND_FIELDS = ("brand_name", "tone", "target_audience", "product_category", "keywords")

_DEFAULT_TITLE = "새 채팅"
_INFER_LIMIT = 5
_INFER_MIN_INPUTS = 2


def _utcnow() -> datetime:
    """naive UTC — DB의 created_at(server_default=func.now(), UTC)과 같은 기준으로 저장.
    로컬 KST 머신의 datetime.now()(naive 로컬)와 달리 타임존이 일관돼 프론트 KST 변환이 맞다."""
    return datetime.now(UTC).replace(tzinfo=None)


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


async def count_advice_usage(project_id: str | None) -> int:
    """프로젝트의 비광고(일반 업무) 답변 수 — meta.usage_type='advice' COUNT(P12 한도)."""
    pid = _as_uuid(project_id)
    if pid is None:
        return 0
    try:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("""
                    SELECT COUNT(m.id)
                    FROM chat_messages m
                    JOIN chat_sessions s ON s.id = m.session_id
                    WHERE s.project_id = :pid
                      AND m.role = 'assistant'
                      AND m.metadata->>'usage_type' = 'advice'
                """),
                {"pid": str(pid)},
            )
            return int(row.scalar() or 0)
    except Exception:  # noqa: BLE001 — 카운트 실패가 채팅을 막지 않게
        return 0


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
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "meta": m.meta,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
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
    session.updated_at = _utcnow()
    await db.commit()
    # 10턴 초과 시 앞 대화를 요약·압축(best-effort, 모크/키 없으면 생략).
    await summarize_and_compress(str(sid), str(session.project_id) if session.project_id else None)


async def append_widget_messages(session_id: str, items: list[dict]) -> list[dict]:
    """단독 어시스턴트 위젯 메시지 여러 개를 세션에 적재(사용자 발화 없이). 저장된 메시지 반환.

    시뮬 완료 후 결과 요약·토론 위젯을 별도 메시지로 DB에 남겨 새로고침 복원을 가능케 한다.
    items: [{"content": str, "meta": {...}}]. created_at을 ms 단위로 증가시켜 표시 순서를 보장.
    """
    sid = _as_uuid(session_id)
    if sid is None or not items:
        return []
    try:
        async with AsyncSessionLocal() as db:
            session = await db.get(ChatSession, sid)
            if session is None:
                return []
            base = _utcnow()
            models: list[ChatMessage] = []
            for i, it in enumerate(items):
                m = ChatMessage(
                    session_id=sid,
                    role="assistant",
                    content=str(it.get("content") or ""),
                    meta=it.get("meta") or None,
                    created_at=base + timedelta(milliseconds=i),
                )
                db.add(m)
                models.append(m)
            session.updated_at = base + timedelta(milliseconds=len(items))
            await db.commit()
            for m in models:
                await db.refresh(m)
            return [
                {"id": str(m.id), "role": m.role, "content": m.content, "meta": m.meta}
                for m in models
            ]
    except Exception as exc:  # noqa: BLE001 — 영속화 실패가 채팅을 막지 않게
        print(f"[chat] append widget messages error: {exc!r}")
        return []


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
        from langsmith.wrappers import wrap_openai  # noqa: PLC0415
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = wrap_openai(AsyncOpenAI(api_key=key))
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


def _memory_text(memory_type: str, content: dict) -> str:
    """롱텀 메모리 1건을 임베딩·검색용 평문으로 직렬화(타입별 핵심 필드만)."""
    c = content or {}
    if memory_type == "sim_input":
        return (
            f"시뮬 입력 제목 {c.get('ad_title', '')} 카피 {c.get('ad_content', '')} "
            f"카테고리 {c.get('product_category', '')} 목표 {c.get('ad_objective', '')}"
        )
    if memory_type == "gen_input":
        return (
            f"생성 입력 상품 {c.get('product_name', '')} 설명 {c.get('product_description', '')} "
            f"타깃 {c.get('target_audience', '')} 목표 {c.get('campaign_objective', '')}"
        )
    if memory_type == "session_summary":
        return f"이전 대화 요약 {c.get('summary', '')}"
    if memory_type == "user_profile_inferred":
        return f"사용자 프로파일 {c.get('profile') or c}"
    return str(c)


async def _embed_memory(text: str) -> list[float] | None:
    """메모리/질문 텍스트 임베딩(풀모드+키일 때만). 미설정·실패·빈 텍스트면 None(폴백 유도)."""
    from core.config import settings  # noqa: PLC0415 — 지연 임포트(설정 의존 최소화)

    key = getattr(settings, "openai_api_key", None)
    if getattr(settings, "use_mock", True) or not key or not text.strip():
        return None
    try:
        from langsmith.wrappers import wrap_openai  # noqa: PLC0415
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = wrap_openai(AsyncOpenAI(api_key=key))
        resp = await client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
        return resp.data[0].embedding
    except Exception as exc:  # noqa: BLE001 — 임베딩 실패가 저장/검색을 막지 않게
        print(f"[chat] memory embed error: {exc!r}")
        return None


async def save_long_term_memory(
    project_id: str | None,
    memory_type: str,
    content: dict,
    user_id: str | None = None,
) -> None:
    """롱텀 메모리 1건 적재(best-effort) — 자체 세션. 오케스트레이터(비요청 스코프)에서 호출.

    시맨틱 검색용 임베딩을 함께 채운다(풀모드+키일 때만, 실패 시 NULL로 저장 — 조회는 최신순 폴백).
    """
    pid = _as_uuid(project_id)
    if pid is None:
        return  # 프로젝트 스코프 없으면 누적 의미 없음 — 생략
    embedding = await _embed_memory(_memory_text(memory_type, content))
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                ChatLongTermMemory(
                    project_id=pid,
                    user_id=_as_uuid(user_id),
                    memory_type=memory_type,
                    content=content,
                    embedding=embedding,
                )
            )
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — 메모리 적재 실패가 채팅을 막지 않게
        print(f"[chat] long-term memory save error: {exc!r}")


async def search_long_term_memory(
    project_id: str | None, query: str, k: int = 4, memory_type: str | None = None
) -> list[dict]:
    """질문과 의미적으로 가까운 롱텀 메모리 top-k(pgvector 코사인).

    임베딩/키 없음·실패 시 get_long_term_memory(최신순)로 폴백 — 항상 무언가는 돌려준다.
    """
    pid = _as_uuid(project_id)
    if pid is None:
        return []
    emb = await _embed_memory(query)
    if emb is None:
        return await get_long_term_memory(project_id, limit=k, memory_type=memory_type)
    try:
        async with AsyncSessionLocal() as db:
            dist = ChatLongTermMemory.embedding.cosine_distance(emb).label("dist")
            stmt = select(ChatLongTermMemory, dist).where(
                ChatLongTermMemory.project_id == pid,
                ChatLongTermMemory.embedding.isnot(None),
            )
            if memory_type:
                stmt = stmt.where(ChatLongTermMemory.memory_type == memory_type)
            rows = (await db.execute(stmt.order_by(dist).limit(k))).all()
            return [
                {
                    "memory_type": r[0].memory_type,
                    "content": r[0].content,
                    "created_at": r[0].created_at.isoformat() if r[0].created_at else None,
                    "score": round(1.0 - float(r[1]), 3),
                }
                for r in rows
            ]
    except Exception as exc:  # noqa: BLE001 — 검색 실패면 최신순 폴백
        print(f"[chat] long-term memory search error: {exc!r}")
        return await get_long_term_memory(project_id, limit=k, memory_type=memory_type)


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


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _top_nonempty(values: list[str]) -> str:
    cleaned = [v for v in (_clean_text(v) for v in values) if v]
    if not cleaned:
        return ""
    return Counter(cleaned).most_common(1)[0][0]


def _top_keywords(values: list[str], limit: int = 6) -> list[str]:
    items: list[str] = []
    for value in values:
        text = _clean_text(value)
        if not text:
            continue
        for sep in ("/", ",", "·", "|"):
            text = text.replace(sep, " ")
        items.extend(part.strip() for part in text.split() if len(part.strip()) >= 2)
    return [word for word, _ in Counter(items).most_common(limit)]


def _profile_from_execution_memory(rows: list[dict]) -> dict:
    contents = [r.get("content") or {} for r in rows]
    categories: list[str] = []
    targets: list[str] = []
    objectives: list[str] = []
    product_terms: list[str] = []
    for content in contents:
        categories.append(_clean_text(content.get("product_category")))
        targets.append(_clean_text(content.get("target_audience")))
        objective = content.get("ad_objective") or content.get("campaign_objective")
        objectives.append(_clean_text(objective))
        product_terms.append(_clean_text(content.get("product_name") or content.get("ad_title")))
        product_text = content.get("product_description") or content.get("ad_content")
        product_terms.append(_clean_text(product_text))
    category = _top_nonempty(categories)
    target = _top_nonempty(targets)
    keywords = _top_keywords(product_terms + categories + targets + objectives)
    tone = "성과 중심" if "conversion" in objectives or "전환" in objectives else ""
    brand_name = _top_nonempty(product_terms)[:200]
    return {
        "brand_name": brand_name,
        "tone": tone,
        "target_audience": target,
        "product_category": category,
        "keywords": keywords,
    }


async def infer_profile_from_execution_history(project_id: str | None) -> dict | None:
    """최근 시뮬·생성 실행 입력을 집계해 프로젝트 브랜드 프로파일을 추론한다."""
    sim_rows = await get_long_term_memory(project_id, limit=_INFER_LIMIT, memory_type="sim_input")
    gen_rows = await get_long_term_memory(project_id, limit=_INFER_LIMIT, memory_type="gen_input")
    rows = sorted(
        sim_rows + gen_rows,
        key=lambda item: item.get("created_at") or "",
        reverse=True,
    )[:_INFER_LIMIT]
    if len(rows) < _INFER_MIN_INPUTS:
        return None
    profile = _profile_from_execution_memory(rows)
    updates = {k: v for k, v in profile.items() if v}
    if not updates:
        return None
    await upsert_brand_profile(project_id, updates)
    evidence = {
        "source_types": [r.get("memory_type") for r in rows],
        "sample_count": len(rows),
        "profile": updates,
    }
    await save_long_term_memory(project_id, "user_profile_inferred", evidence)
    return evidence


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
