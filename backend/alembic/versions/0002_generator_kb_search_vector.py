# 생성 KB 하이브리드 검색용 tsvector 생성열·GIN 인덱스 추가 (management와 동일 패턴)
"""generator_kb_chunks에 search_vector(GENERATED STORED)와 GIN 인덱스를 더한다.

management_kb_chunks(0001_baseline)와 동일하게 ORM 미매핑 — retriever raw SQL만 사용.
STORED 생성열이라 기존 청크는 ALTER 시점에 자동 백필(재적재 불필요).
"""

from alembic import op

revision = "0002_generator_kb_search_vector"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE generator_kb_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_gen_kb_chunks_search "
        "ON generator_kb_chunks USING GIN (search_vector)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_gen_kb_chunks_search")
    op.execute("ALTER TABLE generator_kb_chunks DROP COLUMN IF EXISTS search_vector")
