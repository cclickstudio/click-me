"""add embedding column to chat_long_term_memory

Revision ID: 026
Revises: 025
Create Date: 2026-06-25

채팅 롱텀 메모리 시맨틱 검색 — pgvector 임베딩 컬럼(nullable) 추가.
기존 행은 NULL로 남고 조회 시 최신순 폴백, 신규 저장부터 임베딩 채움.
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("ALTER TABLE chat_long_term_memory ADD COLUMN IF NOT EXISTS embedding vector(1536)")


def downgrade() -> None:
    op.execute("ALTER TABLE chat_long_term_memory DROP COLUMN IF EXISTS embedding")
