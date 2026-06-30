"""add created_campaigns.simulation_id — 집행 전 시뮬 예측 연결용

Revision ID: 021
Revises: 020
Create Date: 2026-06-22

캠페인이 어떤 시뮬 런(simulations.id)으로 집행됐는지 저장해, 예측(전)↔실측(후) 비교에서
정확히 매칭한다. creative_ad_id(Meta 재사용)와 별도 컬럼. 기존 행은 NULL(시뮬 미연결).
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE created_campaigns ADD COLUMN IF NOT EXISTS simulation_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE created_campaigns DROP COLUMN IF EXISTS simulation_id")
