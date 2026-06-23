"""add brand_kits table

Revision ID: 021
Revises: 020
Create Date: 2026-06-23

원래 019였으나 머지 시 채팅 마이그레이션(019·020)과 리비전 충돌 → 020 뒤로 재번호.
"""

from alembic import op

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 브랜드 키트 — 조직 단위로 색·로고·톤을 명명 저장(여러 개 보유·선택)
    op.execute("""
        CREATE TABLE IF NOT EXISTS brand_kits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id),
            name VARCHAR(100) NOT NULL,
            brand_color VARCHAR(20),
            brand_logo_key VARCHAR(512),
            tone_and_manner TEXT,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_brand_kits_org ON brand_kits(organization_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS brand_kits")
