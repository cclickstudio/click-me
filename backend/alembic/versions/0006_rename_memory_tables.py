# 메모리 테이블 개명 — 롱텀 메모리 일원화 1단계(정체에 맞는 이름으로)
"""rename memory tables

Revision ID: 0006_rename_memory_tables
Revises: 0004_generator_kb_search_vector
Create Date: 2026-07-03

- chat_long_term_memory → chat_session_summaries (세션 요약 전용으로 축소 예정)
- execution_history → chat_execution_history (기능 수행 이력 = 채팅 에이전트의 롱텀 메모리)

빈 DB는 0001_baseline의 create_all이 개명 후 ORM대로 새 이름으로 바로 생성하므로,
기존 DB(옛 이름 존재)에서만 rename이 실행되게 전부 멱등 가드.

주의: 팀원이 0005 작업 중 — 0005 머지 후 down_revision을 그 revision id로 갱신할 것.
"""

import sqlalchemy as sa

from alembic import op

revision = "0006_rename_memory_tables"
down_revision = "0004_generator_kb_search_vector"
branch_labels = None
depends_on = None

_TABLE_RENAMES = [
    ("chat_long_term_memory", "chat_session_summaries"),
    ("execution_history", "chat_execution_history"),
]
_INDEX_RENAMES = [
    ("ix_chat_ltm_project", "ix_chat_session_summaries_project"),
    ("ix_execution_history_search_tsv", "ix_chat_execution_history_search_tsv"),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for old, new in _TABLE_RENAMES:
        if insp.has_table(old) and not insp.has_table(new):
            op.rename_table(old, new)
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {old} RENAME TO {new}")


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for old, new in _TABLE_RENAMES:
        if insp.has_table(new) and not insp.has_table(old):
            op.rename_table(new, old)
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {new} RENAME TO {old}")
