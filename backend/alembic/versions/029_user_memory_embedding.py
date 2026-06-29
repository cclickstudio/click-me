"""management_user_memory.embedding — 장기기억 시맨틱 회수용 임베딩 컬럼

Revision ID: 029
Revises: 028
Create Date: 2026-06-28

장기기억 회수를 recency(최신순)에서 임베딩 시맨틱 top-k로 올리기 위한 컬럼(M6, 도연 패턴).
추가형(비파괴) — nullable, 기존 행/코드 무영향. 임베딩 없는 행은 recency 폴백으로 회수된다.
text-embedding-3-small(1536) — KB·ad 임베딩과 동일 차원.
"""

from alembic import op

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        "ALTER TABLE management_user_memory ADD COLUMN IF NOT EXISTS embedding vector(1536)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE management_user_memory DROP COLUMN IF EXISTS embedding")
