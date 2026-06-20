"""add brand recognition (Fluency) columns — REPORT §2-5

Revision ID: 010
Revises: 009
Create Date: 2026-06-18

브랜드 식별(Fluency, REPORT §2-5) 정합 — 기존 테이블에 컬럼만 additive 추가(IF NOT EXISTS, 비파괴).
- persona_responses.brand_recognized : 어느 브랜드/제품 광고인지 명확히 식별했는가(가중 집계 입력)
- persona_responses.perceived_brand  : 인식한 브랜드/제품명(선언 의도와 대조해 오귀속 분해)
- simulation_aggregates.brand_recognition_rate : QA 통과분 가중 식별률(§2-5)
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE persona_responses "
        "ADD COLUMN IF NOT EXISTS brand_recognized BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS perceived_brand VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE simulation_aggregates "
        "ADD COLUMN IF NOT EXISTS brand_recognition_rate NUMERIC(5,4) NOT NULL DEFAULT 0.0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE simulation_aggregates DROP COLUMN IF EXISTS brand_recognition_rate")
    op.execute("ALTER TABLE persona_responses DROP COLUMN IF EXISTS perceived_brand")
    op.execute("ALTER TABLE persona_responses DROP COLUMN IF EXISTS brand_recognized")
