# 체크포인터 — URL 변환(hermetic) + AsyncPostgresSaver setup·roundtrip(Postgres 게이트).
import asyncio
import os
import sys
import uuid

import pytest

from domain.chat.checkpointer import to_psycopg_conninfo
from tests.chat.conftest import pg_only


# psycopg3 async는 Windows ProactorEventLoop 미지원 → SelectorEventLoop 강제.
# TODO: pytest-asyncio fixture 오버라이드는 deprecated — 후속에 loop_factory 방식으로 이전.
@pytest.fixture
def event_loop_policy():
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def test_to_psycopg_conninfo_strips_asyncpg():
    out = to_psycopg_conninfo("postgresql+asyncpg://u:p@h/db?sslmode=require")
    assert out.startswith("postgresql://")
    assert "+asyncpg" not in out
    assert "sslmode=require" in out


@pg_only
@pytest.mark.asyncio
async def test_checkpointer_setup_and_roundtrip():
    from langgraph.checkpoint.base import empty_checkpoint

    from domain.chat.checkpointer import build_async_checkpointer

    saver, close = await build_async_checkpointer(os.environ["CHAT_TEST_DB_URL"])
    thread_id = f"chat-3a-test-{uuid.uuid4().hex[:8]}"  # per-run 격리
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    try:
        cp = empty_checkpoint()
        await saver.aput(config, cp, {}, {})
        got = await saver.aget(config)
        assert got is not None and got["id"] == cp["id"]
    finally:
        await saver.adelete_thread(thread_id)  # 공유 DB 잔여 checkpoints* 정리(자기정리 불변식)
        await close()
