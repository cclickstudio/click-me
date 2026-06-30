"""add ad_templates table

Revision ID: 024
Revises: 023
Create Date: 2026-06-24

광고 설정 템플릿 — 자주 쓰는 시뮬/생성 입력을 명명 저장해 재사용(T12).
"""

from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ad_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            template_type VARCHAR(10) NOT NULL,
            content JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ad_templates_project ON ad_templates(project_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ad_templates")
