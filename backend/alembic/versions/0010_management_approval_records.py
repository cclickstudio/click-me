# 승인 원장 테이블(management_approval_records) 신설 — 집행 게이트 #5(승인 위조 방지)
"""add management_approval_records table + indexes

Revision ID: 0010_management_approval_records
Revises: 0009_center_suggestions
Create Date: 2026-07-07

스펙: docs/superpowers/specs/2026-06-19-management-remediation-actuator-design.md §3.3.
서버가 발행한 ApprovedAction의 스냅샷 원장 — executor가 /execute 제출본과 대조해
위조(원장 부재·필드 불일치, 특히 execution_mode LIVE 바꿔치기)를 차단한다.
빈 DB는 0001_baseline의 create_all이 ORM(ApprovalRecordRow)대로 바로 만들고,
아래 멱등 가드(IF NOT EXISTS)가 no-op이 된다. 재실행 안전.
"""

from alembic import op

revision = "0010_management_approval_records"
down_revision = "0009_center_suggestions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS management_approval_records (
            approval_id VARCHAR(64) PRIMARY KEY,
            proposal_id VARCHAR(64) NOT NULL,
            proposal_hash VARCHAR(64) NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            approver_id VARCHAR(64) NOT NULL,
            action_tier INTEGER NOT NULL,
            execution_mode VARCHAR(16) NOT NULL,
            approval_policy_version VARCHAR(64) NOT NULL,
            expected_state_version VARCHAR(64) NOT NULL,
            approved_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mgmt_approval_proposal "
        "ON management_approval_records (proposal_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mgmt_approval_tenant "
        "ON management_approval_records (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS management_approval_records")
