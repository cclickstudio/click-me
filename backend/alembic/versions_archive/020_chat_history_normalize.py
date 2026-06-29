"""normalize chat history — chat_sessions에 title·updated_at, messages JSONB → chat_messages 이관

Revision ID: 020
Revises: 019
Create Date: 2026-06-23

채팅 내역을 프로젝트별 세션 목록 + 정규화 메시지로 영속화한다. 기존 chat_sessions.messages
(JSONB 배열)를 chat_messages 행으로 옮기고(순서 보존), 세션엔 title·updated_at을 둔다.
chat_messages 테이블은 001에서 이미 생성됨(여기선 데이터 이관만).
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 세션 목록 표시용 컬럼 — 제목과 최근 활동 시각.
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title VARCHAR(200) NOT NULL DEFAULT '새 채팅'"
    )
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT NOW()"
    )
    # 기존 messages JSONB 배열 → chat_messages 행(순서는 ordinality로 created_at에 반영).
    op.execute("""
        INSERT INTO chat_messages (session_id, role, content, created_at)
        SELECT s.id,
               (elem->>'role')::chat_role,
               elem->>'content',
               s.created_at + (ord || ' milliseconds')::interval
        FROM chat_sessions s,
             LATERAL jsonb_array_elements(s.messages) WITH ORDINALITY AS t(elem, ord)
        WHERE s.messages IS NOT NULL
          AND jsonb_typeof(s.messages) = 'array'
          AND elem->>'role' IN ('user', 'assistant')
          AND elem->>'content' IS NOT NULL
    """)
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS messages")


def downgrade() -> None:
    # messages 컬럼만 복원(이관 데이터는 되돌리지 않음).
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS messages JSONB DEFAULT '[]'::jsonb"
    )
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS title")
