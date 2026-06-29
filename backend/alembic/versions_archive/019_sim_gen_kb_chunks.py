"""add simulation_kb_chunks·generator_kb_chunks — 시뮬·생성 에이전틱 RAG 지식베이스

Revision ID: 019
Revises: 018
Create Date: 2026-06-23

KPI 정의·해석·방법론(시뮬)과 카피 전략·원칙·톤(생성) 마크다운을 청크·임베딩해
벡터 검색(코사인)으로 근거+인용 제공. 018(management_kb_chunks)과 동일 스키마.
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None

_TABLES = ("simulation_kb_chunks", "generator_kb_chunks")


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for table in _TABLES:
        op.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source VARCHAR(128) NOT NULL,
                title VARCHAR(256) NOT NULL,
                chunk TEXT NOT NULL,
                embedding vector(1536) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table}")
