"""add chat_brand_profiles table

Revision ID: 023
Revises: 022
Create Date: 2026-06-24

채팅 브랜드 프로파일 — 프로젝트마다 브랜드 톤·타겟·카테고리를 기억(매번 입력 불필요).
제너레이터 brand_profiles(client_id PK)와 충돌 방지 위해 별도 테이블.
"""

from alembic import op

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS chat_brand_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
            brand_name VARCHAR(200),
            tone VARCHAR(100),
            target_audience VARCHAR(200),
            product_category VARCHAR(100),
            keywords JSONB,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chat_brand_profiles")
