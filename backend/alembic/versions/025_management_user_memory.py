"""management_user_memory — 세션 넘는 장기기억 (tenant, user) 스코프

Revision ID: 025
Revises: 024
Create Date: 2026-06-25

채팅 어시스턴트의 세션 넘는 장기기억을 영속한다(체크포인터는 thread 단기 전용). 추가형(비파괴) —
기존 테이블·데이터 무영향. (tenant_id, user_id, created_at) 인덱스로 회수.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "management_user_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=True),
        sa.Column("user_id", sa.String(64), nullable=True),
        sa.Column("mem_key", sa.String(128), nullable=False),
        sa.Column("content", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_user_memory_scope",
        "management_user_memory",
        ["tenant_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_memory_scope", table_name="management_user_memory")
    op.drop_table("management_user_memory")
