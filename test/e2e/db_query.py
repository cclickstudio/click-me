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


async def main() -> None:
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "latest-session":
        result = await latest_session(sys.argv[2])
    else:
        raise SystemExit(f"unknown action: {action}")
    # ensure_ascii=True(기본) — Windows 콘솔 인코딩(cp949)에서 한글이 깨지지 않게 \uXXXX로 출력.
    print(json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
