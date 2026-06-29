# chat_sessions.last_read_at 추가 — N5 미확인 알림 집계용(마지막 열람 이후 메시지를 미확인으로)
"""add last_read_at to chat_sessions

Revision ID: 027
Revises: 026
Create Date: 2026-06-26

N5 알림 벨·패널 — 세션별 마지막 열람 시각. NULL이면 전체 미확인. 기존 행은 NULL.
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS last_read_at")
