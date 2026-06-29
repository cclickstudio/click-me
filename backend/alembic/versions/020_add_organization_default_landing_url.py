"""organizations에 default_landing_url 컬럼 추가

Revision ID: 019
Revises: 018
Create Date: 2026-06-22

캠페인 목적지 URL 프리필용 — 조직 기본 랜딩 URL (nullable, 기존 행 영향 없음).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "020"
down_revision: str | Sequence[str] | None = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("default_landing_url", sa.String(length=2048), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("organizations", "default_landing_url")
