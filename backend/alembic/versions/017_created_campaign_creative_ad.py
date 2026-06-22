"""add created_campaigns.creative_ad_id — 집행 전 시뮬 예측 연결용

Revision ID: 017
Revises: 016
Create Date: 2026-06-21

캠페인이 어떤 광고(ad_id)로 만들어졌는지 저장해, 추후 시뮬 예측(전) ↔ 실측(후) 비교에서
정확히 매칭한다. 기존 직접 Meta 캠페인은 NULL(시뮬 미연결).
"""

from alembic import op

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE created_campaigns ADD COLUMN IF NOT EXISTS creative_ad_id VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE created_campaigns DROP COLUMN IF EXISTS creative_ad_id")
