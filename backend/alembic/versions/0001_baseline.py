# 현재 ORM 전체 스키마 baseline — 엉킨 중복 revision(29개) 정리(squash). create_all 기반.
"""squash baseline — current ORM schema (core.Base 40 + SimBase 7 = 47 tables)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-29

기존 001~029(중복 id 다수)를 단일 baseline으로 대체한다. 스키마 진실은 ORM(core.models +
domain.simulation.models). 빈 DB는 이 한 파일로 현재 스키마를 재현하고, 기존 실 DB는 stamp만 한다.
create_all은 checkfirst=True라 멱등 — 이미 있는 테이블은 건너뛴다.
"""

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415
    from domain.simulation.models import SimBase  # noqa: PLC0415

    # core 먼저(ads/projects 등) → SimBase(core를 FK 참조) 순으로 생성.
    CoreBase.metadata.create_all(bind)
    SimBase.metadata.create_all(bind)


def downgrade() -> None:
    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415
    from domain.simulation.models import SimBase  # noqa: PLC0415

    SimBase.metadata.drop_all(bind)
    CoreBase.metadata.drop_all(bind)
