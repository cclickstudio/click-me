# 운영 알림 테이블(management_notifications) 신설 — 이상 감지 C안(하이브리드) 배달 채널
"""add management_notifications table + partial unique dedup index

Revision ID: 0005_management_notifications
Revises: 0006_rename_memory_tables
Create Date: 2026-07-03

스펙: docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md §1.
부분 유니크(resolved_at IS NULL)로 미해결 알림을 dedup_key당 1행으로 강제(멀티워커 백스톱).
전부 멱등 — 재실행 안전.
"""

from alembic import op

revision = "0005_management_notifications"
down_revision = "0006_rename_memory_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS management_notifications (
            id UUID PRIMARY KEY,
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            campaign_id VARCHAR(100),
            kind VARCHAR(60) NOT NULL,
            dedup_key VARCHAR(200) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            read_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            resolution VARCHAR(20),
            consult_session_id UUID,
            last_notified_at TIMESTAMPTZ NOT NULL,
            followup_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mgmt_notif_open_dedup "
        "ON management_notifications (organization_id, kind, dedup_key) "
        "WHERE resolved_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mgmt_notif_org_recent "
        "ON management_notifications (organization_id, last_notified_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS management_notifications")
