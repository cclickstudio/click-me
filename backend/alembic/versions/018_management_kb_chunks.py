"""add management_kb_chunks — 매니지먼트 에이전틱 RAG 지식베이스

Revision ID: 018
Revises: 017
Create Date: 2026-06-21

정책·플레이북·KPI 규칙 마크다운을 청크·임베딩해 벡터 검색(코사인)으로 근거+인용 제공.
"""

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_kb_chunks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source VARCHAR(128) NOT NULL,
            title VARCHAR(256) NOT NULL,
            chunk TEXT NOT NULL,
            embedding vector(1536) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS management_kb_chunks")
