# consult 컨텍스트 주입 — 세션의 최근 상담 meta를 LLM 지시문으로 복원한다 (🅱)
"""프론트는 role/content만 재전송하므로 meta는 DB에서 서버가 회수·주입한다(스펙 §4).
3조건: diagnosed_at TTL 내 · 최근 K 메시지 내 · 최신 1건만 — 미충족이면 주입 안 함.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _build_instruction(meta: dict) -> str:
    lines = []
    for o in meta.get("options", []):
        hint = f" → 도구 {o['tool_hint']}" if o.get("tool_hint") else " (도구 호출 없음 — 관망)"
        lines.append(f"{o['index']}) {o['label']}{hint}")
    return (
        "[진행 중인 이상 조치 상담]\n"
        f"campaign_id={meta.get('campaign_id')} · anomaly={meta.get('anomaly_type')} · "
        f"진단시각={meta.get('diagnosed_at')}\n"
        "옵션:\n" + "\n".join(lines) + "\n"
        "사용자가 번호나 옵션명으로 답하면 위 표의 도구를 campaign_id와 함께 호출해 진행하라. "
        "지출 조치(manage_campaign)는 확인 카드로만 제안하고 직접 실행하지 않는다."
    )


def pick_consult_context(
    messages: list[tuple[dict | None, datetime]],
    *,
    now: datetime,
    ttl_hours: int,
    recent_k: int = 10,
) -> str | None:
    """(meta, created_at) 최신순 목록에서 주입할 컨텍스트를 고른다 — 조건 미충족이면 None.

    4조건: TTL 내 · 최근 K 내 · 최신 1건만 · consult보다 새 위젯 메시지 없음(진행됨 프록시).
    실행 완료는 세션에 안 남지만(스펙 §4) 위젯 '표시'는 meta.widget으로 남는다 — 그걸 쓴다.
    """
    for meta, _created in messages[:recent_k]:
        if meta and "widget" in meta:
            return None  # consult보다 새로운 위젯 = 옵션 진행됨 → 재주입 중단
        if not meta or meta.get("kind") != "remediation_consult":
            continue
        # 최신 1건만 — 첫 매치에서 판정하고 끝낸다(더 과거 consult는 무시).
        try:
            diagnosed = datetime.fromisoformat(str(meta.get("diagnosed_at", "")))
        except ValueError:
            return None
        if now - diagnosed > timedelta(hours=ttl_hours):
            return None
        return _build_instruction(meta)
    return None


async def recall_consult_context(session_id: str, settings: Any) -> str | None:
    """세션 최근 메시지에서 consult 컨텍스트 회수 — 실패는 None(채팅 안 막음)."""
    from datetime import UTC  # noqa: PLC0415

    try:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatMessage  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(ChatMessage.meta, ChatMessage.created_at)
                .where(ChatMessage.session_id == UUID(session_id))
                .order_by(ChatMessage.created_at.desc())
                .limit(10)
            )
            messages = [(m, c) for m, c in rows.all()]
    except Exception:  # noqa: BLE001 — 회수 실패가 답변을 막지 않게
        return None
    return pick_consult_context(
        messages,
        now=datetime.now(UTC),
        ttl_hours=getattr(settings, "management_consult_context_ttl_hours", 24),
    )
