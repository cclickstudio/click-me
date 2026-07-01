# 현재 ORM 전체 스키마 baseline — 엉킨 중복 revision(29개) 정리(squash). create_all 기반.
"""squash baseline — current ORM schema (core.Base 40 + SimBase 7 = 47 tables)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-29

기존 001~029(중복 id 다수)와 후속 0002(kb 임베딩 1536)·0003(chat 스키마 보정)을 단일
baseline으로 흡수·대체한다. 스키마 진실은 ORM(core.models + domain.simulation.models)이며,
create_all이 0002(Vector(1536))·0003(chat_sessions 컬럼·신규 테이블)을 이미 포함하므로 빈 DB는
이 한 파일로 현재 스키마 전체를 재현하고, 기존 실 DB는 stamp만 한다.
create_all은 checkfirst=True라 멱등 — 이미 있는 테이블은 건너뛴다.
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # chat_messages.role 은 create_type=False 인 네이티브 ENUM이라 create_all이 만들지 않는다.
    # 테이블보다 먼저 멱등 생성(CREATE TYPE에는 IF NOT EXISTS가 없어 DO 블록으로 가드).
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chat_role') THEN
                CREATE TYPE chat_role AS ENUM ('user', 'assistant');
            END IF;
        END $$;
        """
    )

    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415
    from domain.simulation.models import SimBase  # noqa: PLC0415

    # core 먼저(ads/projects 등) → SimBase(core를 FK 참조) 순으로 생성.
    CoreBase.metadata.create_all(bind)
    SimBase.metadata.create_all(bind)

    # users.password_hash는 인증 Cognito 단일화로 ORM에서 제거됨(비번은 Cognito가 단일 관리).
    # create_all은 ORM을 따르므로 빈 DB엔 처음부터 없다. 이전 스키마(컬럼 존재)인 DB를
    # baseline으로 올릴 때만 대비해 멱등 drop — 있으면 제거, 없으면 no-op.
    insp = sa.inspect(bind)
    if any(c["name"] == "password_hash" for c in insp.get_columns("users")):
        op.drop_column("users", "password_hash")


def downgrade() -> None:
    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415
    from domain.simulation.models import SimBase  # noqa: PLC0415

    SimBase.metadata.drop_all(bind)
    CoreBase.metadata.drop_all(bind)
    op.execute("DROP TYPE IF EXISTS chat_role")
