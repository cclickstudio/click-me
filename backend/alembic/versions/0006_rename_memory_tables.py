# 메모리 테이블 정리 — 롱텀 메모리 일원화(개명 + LLM 추출 기억 테이블 drop)
"""rename memory tables + drop management_user_memory

Revision ID: 0006_rename_memory_tables
Revises: 0004_generator_kb_search_vector
Create Date: 2026-07-03

- chat_long_term_memory → chat_session_summaries (세션 요약 전용으로 축소)
- execution_history → chat_execution_history (기능 수행 이력 = 채팅 에이전트의 롱텀 메모리)
- management_user_memory drop — remember/recall(LLM 큐레이션 장기기억) 경로 제거로 읽는 곳 없음.
  롱텀은 chat_execution_history 하나로 일원화, 선호는 chat_brand_profiles.

빈 DB는 0001_baseline의 create_all이 개명 후 ORM대로 새 이름으로 바로 생성하므로,
기존 DB(옛 이름 존재)에서만 rename/drop이 실행되게 전부 멱등 가드.

주의: 0006이 먼저 DB에 적용됨(2026-07-03) — 팀원의 0005_management_notifications는
down_revision을 "0006_rename_memory_tables"로 잡아야 한다(체인: 0004 → 0006 → 0005).
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
    ("ix_execution_history_project_id", "ix_chat_execution_history_project_id"),
]


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for old, new in _TABLE_RENAMES:
        if insp.has_table(old) and not insp.has_table(new):
            op.rename_table(old, new)
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {old} RENAME TO {new}")
    op.execute("DROP TABLE IF EXISTS management_user_memory")  # 인덱스는 테이블과 함께 삭제


def downgrade() -> None:
    insp = sa.inspect(op.get_bind())
    for old, new in _TABLE_RENAMES:
        if insp.has_table(new) and not insp.has_table(old):
            op.rename_table(new, old)
    for old, new in _INDEX_RENAMES:
        op.execute(f"ALTER INDEX IF EXISTS {new} RENAME TO {old}")
    # 복구용 최소 스키마(데이터는 복구 불가) — 구 0001_baseline ORM 정의와 동일 구성.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS management_user_memory (
            id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id varchar(64),
            user_id varchar(64),
            mem_key varchar(128) NOT NULL,
            content jsonb NOT NULL DEFAULT '{}'::jsonb,
            embedding vector(1536),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_user_memory_scope "
        "ON management_user_memory (tenant_id, user_id, created_at)"
    )
