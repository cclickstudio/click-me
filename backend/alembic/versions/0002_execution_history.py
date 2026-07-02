# 실행 히스토리 테이블 — 기능 수행 이력(시간·종류·데이터) + tsvector BM25급 키워드 색인
"""execution_history — feature run log with tsvector keyword index

Revision ID: 0002_execution_history
Revises: 0001_baseline
Create Date: 2026-07-02

baseline(0001)의 create_all은 현재 ORM 전체를 재현하므로 신규 DB는 이 테이블도 이미 생성된다.
baseline에서 stamp된 기존 실 DB만 이 마이그로 테이블을 얻으면 되므로 전부 IF NOT EXISTS 멱등으로
작성한다(신규 DB에선 no-op). ORM(core.models.ExecutionHistory)과 스키마를 일치시킨다.
"""

from alembic import op

revision = "0002_execution_history"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS execution_history (
            id           uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
            project_id   uuid REFERENCES projects(id) ON DELETE CASCADE,
            user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
            executed_at  timestamptz NOT NULL DEFAULT now(),
            feature_type varchar(20) NOT NULL,
            action       varchar(64) NOT NULL,
            summary      text NOT NULL DEFAULT '',
            payload      jsonb NOT NULL DEFAULT '{}'::jsonb,
            search_tsv   tsvector GENERATED ALWAYS AS
                             (to_tsvector('simple', coalesce(summary, ''))) STORED
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_execution_history_project_id "
        "ON execution_history (project_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_execution_history_search_tsv "
        "ON execution_history USING GIN (search_tsv)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_execution_history_search_tsv")
    op.execute("DROP INDEX IF EXISTS ix_execution_history_project_id")
    op.execute("DROP TABLE IF EXISTS execution_history")
