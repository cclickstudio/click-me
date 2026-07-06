# 메모리 테이블 정리 — 롱텀 메모리 일원화(개명 + LLM 추출 기억 테이블 drop)
"""rename memory tables + drop management_user_memory

Revision ID: 0005_rename_memory_tables
Revises: 0004_generator_kb_search_vector
Create Date: 2026-07-03

- chat_long_term_memory → chat_session_summaries (세션 요약 전용으로 축소)
- execution_history → chat_execution_history (기능 수행 이력 = 채팅 에이전트의 롱텀 메모리)
- management_user_memory drop — remember/recall(LLM 큐레이션 장기기억) 경로 제거로 읽는 곳 없음.
  롱텀은 chat_execution_history 하나로 일원화, 선호는 chat_brand_profiles.
- automation_runs 생성(3도메인 공용 자동화 워커 결과 저장소) — 통합(멱등 IF NOT EXISTS).

빈 DB는 0001_baseline의 create_all이 개명 후 ORM대로 새 이름으로 바로 생성하므로,
기존 DB(옛 이름 존재)에서만 rename/drop이 실행되게 전부 멱등 가드.

이력: 이 리비전은 원래 0006으로 먼저 DB 적용됐고(2026-07-03) management_notifications가
0005였다. 이후 번호를 실제 적용 순서에 맞춰 정렬(체인: 0004 → 0005(이 파일) → 0006).
"""

import sqlalchemy as sa

from alembic import op

revision = "0005_rename_memory_tables"
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

    # automation_runs — 자동화(APScheduler 워커) 실행 결과 공용 저장소(3도메인 공용). 006에 통합.
    # 신규 DB는 0001_baseline의 create_all이 ORM(core.models.AutomationRun)대로 생성하므로
    # 여기선 멱등(IF NOT EXISTS)으로 중복 안전. 컬럼·인덱스는 ORM 정의와 동일하게 맞춘다.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS automation_runs (
            id uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            domain varchar(20) NOT NULL,
            job_name varchar(64) NOT NULL,
            project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
            org_id uuid,
            status varchar(16) NOT NULL DEFAULT 'finding',
            severity varchar(16),
            title varchar(200) NOT NULL DEFAULT '',
            body text NOT NULL DEFAULT '',
            suggested_action varchar(64),
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            dedup_key varchar(200),
            actor varchar(16) NOT NULL DEFAULT 'auto',
            created_at timestamptz NOT NULL DEFAULT now(),
            resolved_at timestamptz
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_automation_runs_domain_project "
        "ON automation_runs (domain, project_id, created_at DESC)"
    )
    # 미해결(resolved_at IS NULL) 알림은 dedup_key당 1행 — 부분 유니크(재통지 방지).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_automation_runs_dedup_open "
        "ON automation_runs (dedup_key) WHERE resolved_at IS NULL AND dedup_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation_runs")  # 006 통합분 — 인덱스도 함께 삭제

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
