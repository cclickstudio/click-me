# 기존 DB 드리프트 복구 — chat_sessions 누락 컬럼 + 누락 테이블(create_all)을 ORM에 맞춤
"""reconcile chat schema drift to ORM

Revision ID: 0003_reconcile_chat_schema
Revises: 0002_kb_embedding_1536
Create Date: 2026-06-29

baseline(0001)을 stamp만 한 기존 DB는 create_all이 실행되지 않아, doyeon 챗봇 작업으로
ORM에 추가된 chat_sessions 컬럼(title·updated_at·last_read_at)과 신규 테이블
(clio_kb_chunks·generator_kb_chunks·chat_brand_profiles·chat_long_term_memory)이 비어 있다.
멱등하게 보정한다 — 빈/최신 DB에선 모두 no-op(IF NOT EXISTS + create_all checkfirst).
"""

from alembic import op

revision = "0003_reconcile_chat_schema"
down_revision = "0002_kb_embedding_1536"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chat_sessions 누락 컬럼 보정(IF NOT EXISTS — 이미 있으면 무시). 기존 행은 DEFAULT로 채움.
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS title varchar(200) NOT NULL DEFAULT '새 채팅'"
    )
    op.execute(
        "ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at timestamp NOT NULL DEFAULT now()"
    )
    op.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS last_read_at timestamp")

    # 누락 테이블 생성 — ORM 기준(checkfirst=True라 이미 있는 테이블은 건너뜀).
    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415

    CoreBase.metadata.create_all(bind)


def downgrade() -> None:
    # 컬럼만 되돌림(테이블 삭제는 데이터 손실 위험이라 보류).
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS last_read_at")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS updated_at")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN IF EXISTS title")
