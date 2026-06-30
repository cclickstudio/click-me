# management_kb_chunks 임베딩 차원 1024(BGE-M3) → 1536(OpenAI text-embedding-3-small)
"""kb embedding dim 1024 -> 1536 (openai)

Revision ID: 0002_kb_embedding_1536
Revises: 0001_baseline
Create Date: 2026-06-29

KB를 OpenAI 임베딩(1536, LTM 테이블과 동일 공간)으로 통일한다. 기존 1024 벡터는 차원이
달라 캐스팅 불가이므로 비우고(kb_ingest가 시작 시 재적재) 컬럼 타입만 1536으로 변경한다.
빈 DB는 0001_baseline의 create_all이 이미 1536으로 생성하므로 이 마이그는 멱등하게 동작한다.
"""

from alembic import op

revision = "0002_kb_embedding_1536"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # documents까지 비워야 kb_ingest의 content_hash skip이 걸리지 않고 전체가 OpenAI로 재적재된다.
    # CASCADE — chunks.document_id FK(ondelete CASCADE)로 chunks도 함께 비워짐.
    op.execute("TRUNCATE TABLE management_kb_documents CASCADE")
    op.execute("ALTER TABLE management_kb_chunks ALTER COLUMN embedding TYPE vector(1536)")


def downgrade() -> None:
    op.execute("TRUNCATE TABLE management_kb_documents CASCADE")
    op.execute("ALTER TABLE management_kb_chunks ALTER COLUMN embedding TYPE vector(1024)")
