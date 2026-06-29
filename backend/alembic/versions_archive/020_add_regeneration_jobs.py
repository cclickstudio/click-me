"""add regeneration_jobs table — 채팅 트리거 재생성 비동기 job 상태

Revision ID: 020
Revises: 019
Create Date: 2026-06-22

core/models.py의 RegenerationJobRow와 1:1. v1 in-process job(설계 2026-06-22 §2).
⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(head 라인) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS regeneration_jobs (
            id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            campaign_id VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            selection_token VARCHAR(64) UNIQUE,
            candidates JSONB,
            selected_candidate_id VARCHAR(64),
            proposal JSONB,
            outcome_reason VARCHAR(48),
            error VARCHAR(512),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_tenant ON regeneration_jobs (tenant_id)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_regen_jobs_campaign ON regeneration_jobs (campaign_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_status ON regeneration_jobs (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_regen_jobs_created ON regeneration_jobs (created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS regeneration_jobs")
