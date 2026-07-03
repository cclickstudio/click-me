# [상담하기] 진입 유스케이스 — 재검증 → 세션 심기(CAS·보상 롤백) → 이동 (🅱)
"""스펙 §4 전이표 구현. 라우터는 반환 dict를 HTTP로 변환만 한다.

재클릭은 재검증 없이 이동 전용(결정) — 재검증은 알림 생성↔첫 상담 갭 해소가 목적이고,
재클릭마다 심으면 세션 스팸. 세션 내 최신 확인은 consult_anomaly 챗 도구가 담당.
CAS(조건부 UPDATE)로 이중 심기 방지 — row lock은 외부 I/O(advisor) 동안 행 잠금을
붙드는 안티패턴이라 채택하지 않음.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_SESSION_TITLE = "⚠ 캠페인 이상 알림"  # chat_sink와 동일 — 프로젝트당 전용 세션 재사용


class DbChatStore:
    """세션 확보·심기·생존 확인 — chat_sink.DbConsultStore 재사용 + 생존 확인 추가."""

    def __init__(self) -> None:
        from domain.management.remediation.chat_sink import DbConsultStore  # noqa: PLC0415

        self._inner = DbConsultStore()

    async def find_or_create_session(self, project_id: str, title: str):
        return await self._inner.find_or_create_session(project_id, title)

    async def append_consult(self, session_id: str, content: str, meta: dict) -> None:
        await self._inner.append_consult(session_id, content, meta)

    async def session_exists(self, session_id: str) -> bool:
        from uuid import UUID  # noqa: PLC0415

        from sqlalchemy import select  # noqa: PLC0415

        from core.db import AsyncSessionLocal  # noqa: PLC0415
        from core.models import ChatSession  # noqa: PLC0415

        async with AsyncSessionLocal() as db:
            row = await db.execute(select(ChatSession.id).where(ChatSession.id == UUID(session_id)))
            return row.first() is not None


async def consult_notification(
    settings: Any,
    notification_id: str,
    org_id: str,
    *,
    store: Any,
    chat_store: Any,
    consult: Any,
    publish: Any,
    now: Any = None,
) -> dict | None:
    """전이표(스펙 §4). None=404(타 org·없음) / unavailable=503 / 나머지 200."""
    now = now or (lambda: datetime.now(UTC))
    n = await store.get(notification_id)
    if n is None or n["organization_id"] != org_id:
        return None  # fail-closed — 존재 여부도 노출하지 않는다

    changed = False  # read·상태 변화(auto_normal·세션 연결) 공용 — finally에서 1회 발행
    if n["read_at"] is None:
        changed = bool(await store.mark_read(org_id, [notification_id], now()))

    try:
        if n["resolved_at"] is not None:
            return {"status": "already_resolved", "resolution": n["resolution"]}

        if n["consult_session_id"]:
            if await chat_store.session_exists(n["consult_session_id"]):
                return {"status": "consult", "session_id": n["consult_session_id"]}
            # 사용자가 세션을 지웠다 — CAS를 비우고 처음부터 재실행(스펙 §4 엣지)
            await store.release_consult_session(notification_id, n["consult_session_id"])

        try:
            result = await consult(settings, n["campaign_id"])
        except Exception:  # noqa: BLE001 — 주입 callable 계약 미보장 방어(암묵→명시, 500→503)
            return {"status": "unavailable"}
        if result is None:
            return {"status": "unavailable"}
        if result.status == "normal":
            await store.resolve(org_id, notification_id, "auto_normal", now())
            changed = True  # 상태 변화(auto_normal) — read 여부와 무관하게 배지 동기화
            return {"status": "normal", "message": result.message}

        session_id, _last_read = await chat_store.find_or_create_session(
            n["project_id"], _SESSION_TITLE
        )
        if await store.claim_consult_session(notification_id, session_id):
            meta = result.to_meta(org_id=org_id)
            try:
                await chat_store.append_consult(session_id, result.message, meta)
            except Exception:  # noqa: BLE001 — 심기 실패는 보상 롤백 후 재시도 가능 응답
                await store.release_consult_session(notification_id, session_id)
                return {"status": "unavailable"}
            changed = True  # 상태 변화(세션 연결) — read 여부와 무관하게 배지 동기화
        else:
            # CAS 패자 — find_or_create 자체의 race로 승자와 다른 세션을 쥘 수 있다.
            # 승자가 확정한 세션을 재조회해 그쪽으로 안내(없으면 방금 세션 폴백).
            latest = await store.get(notification_id)
            session_id = (latest or {}).get("consult_session_id") or session_id
        return {"status": "consult", "session_id": session_id}
    finally:
        if changed:
            publish(org_id)  # read·상태 변화는 어느 경로로 끝나든 1회 배지 동기화(스펙 §4 ①)
