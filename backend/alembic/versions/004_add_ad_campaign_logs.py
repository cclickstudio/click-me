"""add ad_campaign_logs table

Revision ID: 004
Revises: 003
Create Date: 2026-06-14
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ad_campaign_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            generation_id UUID REFERENCES ad_generations(id) ON DELETE SET NULL,
            candidate_id UUID REFERENCES ad_generation_candidates(id) ON DELETE SET NULL,
            status VARCHAR(20) NOT NULL,          -- created | failed | mocked
            mocked BOOLEAN NOT NULL DEFAULT FALSE,
            campaign_id VARCHAR(100),
            adset_id VARCHAR(100),
            creative_id VARCHAR(100),
            ad_id VARCHAR(100),
            budget INTEGER,                       -- 일 예산 (원)
            objective VARCHAR(50),
            targeting JSONB,
            request_payload JSONB,
            response_payload JSONB,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ad_campaign_logs_generation
            ON ad_campaign_logs (generation_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ad_campaign_logs")
