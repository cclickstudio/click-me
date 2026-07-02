# personas.weight 컬럼 추가 — DB 기반 고정 패널 조회(§3.6)가 표본가중치를 잃지 않도록.
"""add personas.weight

Revision ID: 0002_persona_weight
Revises: 0001_baseline
Create Date: 2026-07-02

기본 allocation="proportional"·rake_to_census=False(둘 다 기본값)에선 weight가 사실상
1.0(self-weighting)이라 당장 회귀는 없으나, stratified/raking 모드에서 계산된 가중치가
DB 캐시 히트 후 재사용될 때 스키마 기본값(1.0)으로 리셋되는 걸 막기 위한 컬럼.
0001_baseline의 create_all이 이미 이 컬럼으로 테이블을 만드는 빈 DB에서는 멱등 가드로 스킵.
"""

import sqlalchemy as sa

from alembic import op

revision = "0002_persona_weight"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if not any(c["name"] == "weight" for c in insp.get_columns("personas")):
        op.add_column(
            "personas",
            sa.Column("weight", sa.Numeric(10, 4), nullable=False, server_default="1.0"),
        )


def downgrade() -> None:
    op.drop_column("personas", "weight")
