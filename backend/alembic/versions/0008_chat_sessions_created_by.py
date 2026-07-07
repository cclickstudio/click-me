# 채팅 세션 실행자(created_by) 컬럼 신설 — 내역 화면에 세션 개시자 표시용
"""add chat_sessions.created_by

Revision ID: 0008_chat_sessions_created_by
Revises: 0007_ads_generation_id
Create Date: 2026-07-06

chat_sessions에 created_by(uuid FK users.id, NULL 허용)를 추가한다. 세션을 개시한
사용자(실행자)를 기록해 admin 채팅 내역에서 실행자 컬럼을 채운다. 상담/시스템 자동생성
세션은 NULL로 남는다. 빈 DB는 0001_baseline의 create_all이 ORM(core.models.ChatSession)
대로 이미 생성하므로, 기존 실 DB에서만 컬럼을 추가하도록 멱등(IF NOT EXISTS) 가드.
"""

from alembic import op

revision = "0008_chat_sessions_created_by"
down_revision = "0007_ads_generation_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES users(id)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS created_by")
