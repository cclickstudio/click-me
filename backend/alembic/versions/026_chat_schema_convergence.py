"""chat 스키마 수렴 — Phase ③-A (spec §6.2)

chat_sessions: messages jsonb 제거 + user_id/organization_id/title/summary/updated_at 추가 + created_at→timestamptz.
chat_messages: route 추가 + role enum(chat_role)→varchar + session_id 인덱스.
chat_long_term_memory: embedding vector(1024)/salience/last_used_at/source_session_id 추가.
management_kb_chunks: embedding 1536→1024 (KB·LTM 동일 차원 불변식). 데이터 비우고 재적재 필요.

모두 멱등(IF [NOT] EXISTS / ALTER). 개인 DB에서만 적용 — 공용 DB는 팀 합의 후.
chat_role enum은 downgrade(role::chat_role) 복원을 위해 의도적으로 보존(영구 적용 후 정리 시 DROP TYPE).

Revision ID: 026
Revises: 025
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) chat_sessions — 이중화 messages 제거, 세션 메타 추가, created_at naive→timestamptz 통일.
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS messages")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id UUID")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS organization_id UUID")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title VARCHAR(200) DEFAULT '새 채팅'")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS summary TEXT")
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
    )
    op.execute(
        "ALTER TABLE chat_sessions ALTER COLUMN created_at TYPE TIMESTAMPTZ "
        "USING created_at AT TIME ZONE 'UTC'"
    )

    # 2) chat_messages — route 태깅 + role enum(chat_role)→varchar(asyncpg enum insert 회피) + session_id 인덱스.
    op.execute("ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS route VARCHAR(16)")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN role TYPE VARCHAR(16) USING role::text")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_session_id ON chat_messages (session_id)"
    )

    # 3) chat_long_term_memory — 의미 회상 컬럼(024가 기본 테이블 생성)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS embedding vector(1024)")
    op.execute(
        "ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS salience DOUBLE PRECISION NOT NULL DEFAULT 0.5"
    )
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ")
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS source_session_id UUID")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_ltm_salience ON chat_long_term_memory (salience DESC)"
    )

    # 4) management_kb_chunks — 1536→1024 (KB·LTM 동일 차원). 기존 벡터는 차원 불일치라 폐기·재적재.
    op.execute("TRUNCATE TABLE management_kb_chunks")
    op.execute("ALTER TABLE management_kb_chunks ALTER COLUMN embedding TYPE vector(1024)")


def downgrade() -> None:
    # management_kb_chunks 데이터는 upgrade의 TRUNCATE로 소실 — 차원만 복원, 데이터는 재적재 필요(비가역).
    op.execute("ALTER TABLE management_kb_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute("DROP INDEX IF EXISTS ix_chat_ltm_salience")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS source_session_id")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS last_used_at")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS salience")
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS embedding")
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_session_id")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN role TYPE chat_role USING role::chat_role")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS route")
    op.execute(
        "ALTER TABLE chat_sessions ALTER COLUMN created_at TYPE TIMESTAMP "
        "USING created_at AT TIME ZONE 'UTC'"
    )
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS summary")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS title")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS organization_id")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS messages JSONB DEFAULT '[]'::jsonb")
