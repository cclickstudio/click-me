"""add simulation socioeconomic / weight / effective_n columns

Revision ID: 004
Revises: 003
Create Date: 2026-06-14

시뮬레이터 정합(P8/§3.7) — 기존 테이블에 컬럼만 additive 추가(IF NOT EXISTS, 비파괴).
- personas.socioeconomic    : 소득·학력 grounding(KISDI)
- persona_responses.weight  : 표본 가중치(§3.7 가중 집계)
- simulation_aggregates.effective_n : 유효표본수(Kish)
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE personas "
        "ADD COLUMN IF NOT EXISTS socioeconomic JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE persona_responses "
        "ADD COLUMN IF NOT EXISTS weight NUMERIC(10,4) NOT NULL DEFAULT 1.0"
    )
    op.execute(
        "ALTER TABLE simulation_aggregates "
        "ADD COLUMN IF NOT EXISTS effective_n NUMERIC(10,1) NOT NULL DEFAULT 0.0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE simulation_aggregates DROP COLUMN IF EXISTS effective_n")
    op.execute("ALTER TABLE persona_responses DROP COLUMN IF EXISTS weight")
    op.execute("ALTER TABLE personas DROP COLUMN IF EXISTS socioeconomic")
