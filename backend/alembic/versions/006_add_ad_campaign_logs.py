"""add ad_campaign_logs table

Revision ID: 006
Revises: 005
Create Date: 2026-06-14

주의: 원래 revision id가 004로, 004_add_simulation_weight_socioeconomic 과 중복되어
alembic 그래프가 멀티헤드로 깨져 있었다. 선형화를 위해 005 뒤 006으로 재배치(테이블은
CREATE TABLE IF NOT EXISTS라 이미 생성됐어도 재적용 안전).
"""

from alembic import op

revision = "006"
down_revision = "005"
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
