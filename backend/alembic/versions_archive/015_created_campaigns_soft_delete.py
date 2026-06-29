"""add deleted_at to created_campaigns — 소프트 삭제(감사 이력 보존)

Revision ID: 015
Revises: 014
Create Date: 2026-06-21

Meta에서 캠페인을 삭제해도 created_campaigns 행은 지우지 않고 deleted_at만 찍어 이력을 남긴다
(감사 로그 원칙 — 만듦→지움이 전부 보존). NULL이면 살아있는 기록.

⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(head 라인) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE created_campaigns ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE created_campaigns DROP COLUMN IF EXISTS deleted_at")
