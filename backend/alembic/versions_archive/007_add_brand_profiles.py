"""add brand_profiles table

Revision ID: 007
Revises: 006
Create Date: 2026-06-17
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 제너레이터 브랜드 설정 — 로그인 없이 client_id(브라우저 UUID)로 식별·영속
    op.execute("""
        CREATE TABLE IF NOT EXISTS brand_profiles (
            client_id VARCHAR(64) PRIMARY KEY,
            brand_color VARCHAR(20),
            brand_logo_key VARCHAR(512),
            tone_and_manner TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS brand_profiles")
