# 센터 제안 알림 테이블(center_suggestions) 신설 — 크로스도메인 인라인 제안 저장소
"""add center_suggestions table + indexes

Revision ID: 0007_center_suggestions
Revises: 0006_management_notifications
Create Date: 2026-07-06

스펙: docs/center/center-spec.md §5·§8.
시뮬/제너 잡 완료 직후 인라인 생성되는 제안 알림(시뮬레이션 제안·제너레이터 제안·집행 제안).
management 이상감지(management_notifications)와 별개 테이블 — 알림 센터가 양쪽 병합 조회.
빈 DB는 0001_baseline의 create_all이 ORM(CenterSuggestion)대로 바로 만들고, 아래 멱등
가드(IF NOT EXISTS)가 no-op이 된다. 재실행 안전.
"""

from alembic import op

revision = "0007_center_suggestions"
down_revision = "0006_management_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS center_suggestions (
            id UUID PRIMARY KEY,
            suggestion_type VARCHAR(40) NOT NULL,
            reason VARCHAR(200),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            source_sim_id UUID,
            source_gen_id UUID,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            read_at TIMESTAMPTZ,
            dismissed_at TIMESTAMPTZ,
            dedup_key VARCHAR(200),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_center_suggest_org_recent "
        "ON center_suggestions (organization_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_center_suggest_project "
        "ON center_suggestions (project_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_center_suggest_open_dedup "
        "ON center_suggestions (dedup_key) "
        "WHERE dismissed_at IS NULL AND dedup_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS center_suggestions")
