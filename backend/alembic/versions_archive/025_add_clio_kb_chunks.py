# CLIO 전용 지식베이스 테이블을 추가하는 Alembic 마이그레이션
"""add clio_kb_chunks table

Revision ID: 025
Revises: 024
Create Date: 2026-06-25

CLIO 기본 응답자가 광고 일반 지식을 RAG로 검색할 수 있도록 전용 KB 청크 테이블을 추가한다.
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clio_kb_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("chunk", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("clio_kb_chunks")
