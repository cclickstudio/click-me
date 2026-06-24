# PgChatRepo 세션·메시지 CRUD — 개인 Postgres 게이트.
import uuid

import pytest
from sqlalchemy import delete

from domain.chat.adapters.pg_chat_repo import PgChatRepo
from domain.chat.models import ChatMessage, ChatSession
from tests.chat.conftest import pg_only


@pg_only
@pytest.mark.asyncio
async def test_create_append_and_read(pg_session_factory):
    repo = PgChatRepo(session_factory=pg_session_factory)
    # 알려진 user_id로 격리 — 공유 DB에서도 list_sessions 필터를 결정적으로 검증.
    uid = uuid.uuid4()
    s = await repo.create_session(
        project_id=None, user_id=uid, organization_id=None, title="테스트 세션"
    )
    try:
        m1 = await repo.append_message(
            session_id=s.id, role="user", content="안녕", route=None, meta=None
        )
        await repo.append_message(
            session_id=s.id, role="assistant", content="네", route="management", meta={"k": 1}
        )
        msgs = await repo.get_messages(s.id, limit=10)
        assert [m.role for m in msgs] == ["user", "assistant"]
        assert msgs[1].route == "management" and msgs[1].meta == {"k": 1}
        assert m1.session_id == s.id

        await repo.update_summary(s.id, "요약본")
        got = await repo.get_session(s.id)
        assert got.summary == "요약본"
        assert got.updated_at >= got.created_at  # update_summary가 updated_at 갱신

        sessions = await repo.list_sessions(user_id=uid, limit=5)
        assert [x.id for x in sessions] == [s.id]  # user_id 필터 — 격리된 단일 세션
    finally:
        async with pg_session_factory() as db:
            await db.execute(delete(ChatMessage).where(ChatMessage.session_id == s.id))
            await db.execute(delete(ChatSession).where(ChatSession.id == s.id))
            await db.commit()
