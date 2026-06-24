# 체크포인터 — URL 변환(hermetic) + AsyncPostgresSaver setup·roundtrip(Postgres 게이트).
import asyncio
import os
import sys

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
    try:
        config = {"configurable": {"thread_id": "chat-3a-test-thread", "checkpoint_ns": ""}}
        cp = empty_checkpoint()
        await saver.aput(config, cp, {}, {})
        got = await saver.aget(config)
        assert got is not None and got["id"] == cp["id"]
    finally:
        await close()
