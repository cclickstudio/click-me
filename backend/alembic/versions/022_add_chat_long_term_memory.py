"""add chat_long_term_memory table

Revision ID: 022
Revises: 021
Create Date: 2026-06-24

채팅 롱텀 메모리 — 시뮬/생성 실행 입력·사용자 선호·세션 요약을 프로젝트 단위로 누적.
"""

from alembic import op

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_long_term_memory (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            memory_type VARCHAR(32) NOT NULL,
            content JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_ltm_project "
        "ON chat_long_term_memory(project_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_long_term_memory")
