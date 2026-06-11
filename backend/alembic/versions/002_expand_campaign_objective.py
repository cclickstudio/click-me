"""expand campaign_objective enum

Revision ID: 002
Revises: 001
Create Date: 2026-06-10
"""

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

NEW_VALUES = ("awareness", "conversion", "lead_gen", "app_install", "retention", "product_launch", "promotion")


def upgrade() -> None:
    for value in NEW_VALUES[2:]:  # 기존 awareness, conversion 제외
        op.execute(f"ALTER TYPE campaign_objective ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL은 ENUM 값 제거를 직접 지원하지 않음 — 전체 재생성 필요
    op.execute("""
        ALTER TABLE simulations
            ALTER COLUMN objective TYPE VARCHAR(50);
        DROP TYPE campaign_objective;
        CREATE TYPE campaign_objective AS ENUM ('awareness', 'conversion');
        ALTER TABLE simulations
            ALTER COLUMN objective TYPE campaign_objective
            USING objective::campaign_objective;
    """)
