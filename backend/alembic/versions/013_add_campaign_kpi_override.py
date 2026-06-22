"""add campaign_kpi_overrides table — 조직별 캠페인 수동 KPI(추정 CVR·ROAS)

Revision ID: 013
Revises: 012
Create Date: 2026-06-20

core/models.py의 CampaignKpiOverride와 1:1. 전환 추적 전 캠페인에 고객이 직접 넣는
추정 CVR(전환율 %)·ROAS(배수)를 org+campaign 단위로 영속(스펙: CVR·ROAS 재정의 #2).
실측이 아니라 고객 통계 기반 추정 — 화면에선 '추정'으로 구분 표기.
컬럼 규칙: 타임스탬프=TIMESTAMPTZ / 비율·배수=DOUBLE PRECISION / org+campaign UNIQUE.

⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(head 라인) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS campaign_kpi_overrides (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL
                REFERENCES organizations(id) ON DELETE CASCADE,
            campaign_id VARCHAR(64) NOT NULL,
            cvr DOUBLE PRECISION,
            roas DOUBLE PRECISION,
            updated_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_kpi_override_org_campaign UNIQUE (organization_id, campaign_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS campaign_kpi_overrides")
