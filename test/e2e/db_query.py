# E2E 영속 검증용 DB 조회 헬퍼 — Playwright가 uv로 호출(cwd=backend)해 JSON을 받는다.
# UI만 믿지 않고 실제 ChatSession/ChatMessage(meta.widget)로 위젯 시퀀스를 확인하기 위함.
#
# 사용:
#   uv run python <path>/db_query.py latest-session <project_id>
#     → {"session_id": "...", "widget_types": [...], "ad_titles": [...], "message_count": N}
import asyncio
import json
import os
import sys

# 이 스크립트는 backend 밖(test/e2e)에 있어 uv가 sys.path를 script 디렉터리로 잡는다.
# cwd(=backend)를 경로에 넣어야 core.* 를 import할 수 있다.
sys.path.insert(0, os.getcwd())

from sqlalchemy import text  # noqa: E402

from core.db import AsyncSessionLocal  # noqa: E402


async def latest_session(project_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        sid = await db.scalar(
            text(
                "SELECT id FROM chat_sessions WHERE project_id = :pid "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            {"pid": project_id},
        )
        if sid is None:
            return {"session_id": None, "widget_types": [], "ad_titles": [], "message_count": 0}
        rows = (
            await db.execute(
                text(
                    "SELECT metadata FROM chat_messages WHERE session_id = :sid "
                    "ORDER BY created_at ASC"
                ),
                {"sid": str(sid)},
            )
        ).all()
    widget_types: list[str] = []
    ad_titles: list[str] = []
    for (meta,) in rows:
        if not meta:
            continue
        widget = meta.get("widget") if isinstance(meta, dict) else None
        if not widget:
            continue
        wtype = widget.get("type")
        if wtype:
            widget_types.append(wtype)
        data = widget.get("data") or {}
        if isinstance(data, dict) and data.get("ad_title"):
            ad_titles.append(data["ad_title"])
    return {
        "session_id": str(sid),
        "widget_types": widget_types,
        "ad_titles": ad_titles,
        "message_count": len(rows),
    }


async def recent_completed_sim_ids(project_id: str) -> dict:
    """프로젝트의 최근 48시간 내 COMPLETED 시뮬 id 목록(선제 알림 seen 사전 채움용).

    프런트 api.projects.simulations와 동일한 출처(ads.project_id 조인)를 재현한다.
    """
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text("""
                    SELECT s.id
                    FROM simulations s
                    JOIN ads a ON a.id = s.ad_id
                    WHERE a.project_id = :pid
                      AND s.deleted_at IS NULL
                      AND upper(s.status) = 'COMPLETED'
                      AND s.created_at >= now() - interval '48 hours'
                    ORDER BY s.created_at DESC
                    LIMIT 50
                """),
                {"pid": project_id},
            )
        ).all()
    return {"sim_ids": [str(r.id) for r in rows]}


async def create_session(project_id: str) -> dict:
    """선제 알림 대조용 빈 채팅 세션 B 생성."""
    async with AsyncSessionLocal() as db:
        sid = await db.scalar(
            text(
                "INSERT INTO chat_sessions (id, project_id, title) "
                "VALUES (gen_random_uuid(), :pid, :title) RETURNING id"
            ),
            {"pid": project_id, "title": "[E2E] N4 대조 세션"},
        )
        await db.commit()
    return {"session_id": str(sid)}


async def delete_session(session_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        await db.execute(
            text("DELETE FROM chat_messages WHERE session_id = :sid"), {"sid": session_id}
        )
        await db.execute(text("DELETE FROM chat_sessions WHERE id = :sid"), {"sid": session_id})
        await db.commit()
    return {"ok": True}


async def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "latest-session":
        result = await latest_session(sys.argv[2])
    elif action == "recent-sim-ids":
        result = await recent_completed_sim_ids(sys.argv[2])
    elif action == "create-session":
        result = await create_session(sys.argv[2])
    elif action == "delete-session":
        result = await delete_session(sys.argv[2])
    else:
        raise SystemExit(f"unknown action: {action}")
    # ensure_ascii=True(기본) — Windows 콘솔 인코딩(cp949)에서 한글이 깨지지 않게 \uXXXX로 출력.
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
