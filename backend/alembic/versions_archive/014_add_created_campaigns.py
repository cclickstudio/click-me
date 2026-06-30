"""add created_campaigns table — 앱에서 생성한 캠페인 누적 기록

Revision ID: 014
Revises: 013
Create Date: 2026-06-21

core/models.py의 CreatedCampaign과 1:1. 대시보드는 Meta 실시간 조회지만, 이 표는
"우리가 만든 것"의 이력(삭제돼도 남음). tenant_id는 FK 없는 문자열(데모 테넌트 수용),
meta_campaign_id는 LIVE 생성 시 채워진다.

⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(head 라인) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS created_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(64) NOT NULL,
            meta_campaign_id VARCHAR(64),
            name VARCHAR(255) NOT NULL,
            objective VARCHAR(20) NOT NULL,
            ad_account_id VARCHAR(64) NOT NULL,
            daily_budget_krw INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL,
            execution_mode VARCHAR(20) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS created_campaigns")
