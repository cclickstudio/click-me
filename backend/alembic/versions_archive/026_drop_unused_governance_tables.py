"""drop unused governance tables — action_proposals/approvals/execution_runs/remediation_escalations

Revision ID: 026
Revises: 025
Create Date: 2026-06-26

코드에서 읽기·쓰기 경로가 없는(ORM 정의만 존재) 거버넌스 4종을 제거한다. 인메모리 스토어로만
동작하던 미사용 영속 계층. 실행 감사 이력은 audit_events·idempotency_keys가 계속 담당한다.
downgrade는 008(제안/승인/실행)·011(에스컬레이션) 정의로 동일 스키마를 복원한다(가역).

⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(라인 head=025) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS remediation_escalations")
    op.execute("DROP TABLE IF EXISTS execution_runs")
    op.execute("DROP TABLE IF EXISTS approvals")
    op.execute("DROP TABLE IF EXISTS action_proposals")


def downgrade() -> None:
    # 008_add_management_tables 기준 — 제안/승인/실행
    op.execute("""
        CREATE TABLE IF NOT EXISTS action_proposals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            proposal_id VARCHAR(64) NOT NULL UNIQUE,
            tenant_id VARCHAR(64) NOT NULL,
            ad_account_id VARCHAR(64) NOT NULL,
            action_type VARCHAR(48) NOT NULL,
            action_tier INTEGER NOT NULL,
            status VARCHAR(24) NOT NULL,
            budget_before_krw BIGINT NOT NULL,
            budget_after_krw BIGINT NOT NULL,
            max_total_spend_krw BIGINT NOT NULL,
            expected_state_version VARCHAR(48) NOT NULL,
            proposal_hash VARCHAR(64) NOT NULL,
            approval_policy_version VARCHAR(16) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            payload JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_action_proposals_tenant ON action_proposals (tenant_id)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_proposals_status ON action_proposals (status)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_action_proposals_expires ON action_proposals (expires_at)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS approvals (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            approval_id VARCHAR(64) NOT NULL UNIQUE,
            proposal_id VARCHAR(64) NOT NULL,
            proposal_hash VARCHAR(64) NOT NULL,
            tenant_id VARCHAR(64) NOT NULL,
            approver_id VARCHAR(64) NOT NULL,
            action_tier INTEGER NOT NULL,
            approval_policy_version VARCHAR(16) NOT NULL,
            expected_state_version VARCHAR(48) NOT NULL,
            execution_mode VARCHAR(20) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            approved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_approval_idem UNIQUE (proposal_id, approval_policy_version)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_approvals_proposal ON approvals (proposal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_approvals_tenant ON approvals (tenant_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS execution_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id VARCHAR(64) NOT NULL UNIQUE,
            approval_id VARCHAR(64) NOT NULL,
            proposal_id VARCHAR(64) NOT NULL,
            status VARCHAR(24) NOT NULL,
            result_status VARCHAR(24),
            failure_reason VARCHAR(48),
            platform_snapshot JSONB NOT NULL,
            executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_execution_runs_approval ON execution_runs (approval_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_execution_runs_proposal ON execution_runs (proposal_id)"
    )

    # 011_add_remediation_escalation 기준 — 시간축 에스컬레이션 사다리
    op.execute("""
        CREATE TABLE IF NOT EXISTS remediation_escalations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id VARCHAR(64) NOT NULL UNIQUE,
            tenant_id VARCHAR(64) NOT NULL,
            ad_account_id VARCHAR(64) NOT NULL,
            campaign_id VARCHAR(64) NOT NULL,
            anomaly_type VARCHAR(48) NOT NULL,
            ladder JSONB NOT NULL,
            current_rung_index INTEGER NOT NULL DEFAULT 0,
            rung_status VARCHAR(16) NOT NULL,
            rung_executed_at TIMESTAMPTZ,
            last_proposal_id VARCHAR(64),
            last_approval_id VARCHAR(64),
            status VARCHAR(16) NOT NULL,
            opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_evaluated_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_remediation_escalations_tenant "
        "ON remediation_escalations (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_remediation_escalations_campaign "
        "ON remediation_escalations (campaign_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_remediation_escalations_status "
        "ON remediation_escalations (status)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_remediation_escalations_active "
        "ON remediation_escalations (tenant_id, campaign_id) WHERE status = 'active'"
    )
