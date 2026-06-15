"""add management tables (R&R §7) — 제안/승인/감사/실행/멱등키 5종

Revision ID: 006
Revises: 005
Create Date: 2026-06-15

core/models.py의 ActionProposalRow/ApprovalRow/AuditEventRow/ExecutionRunRow/
IdempotencyKeyRow와 1:1. 컬럼 규칙: 타임스탬프=TIMESTAMPTZ / 금액=BIGINT KRW /
유연 페이로드=JSONB / enum=VARCHAR + 앱 레벨 검증.
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 🅱 생산 제안 — 판정·조인 신호는 컬럼, 나머지(evidence·hypothesis 등)는 payload
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
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_proposals_tenant ON action_proposals (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_proposals_status ON action_proposals (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_proposals_expires ON action_proposals (expires_at)")

    # 🅰 승인 기록 — 복합 UNIQUE = 중복승인 멱등 (R&R P2)
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

    # append-only 감사 로그 (게이트 #7)
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(64) NOT NULL,
            proposal_id VARCHAR(64) NOT NULL,
            approval_id VARCHAR(64),
            stage VARCHAR(24) NOT NULL,
            outcome VARCHAR(48) NOT NULL,
            detail JSONB NOT NULL,
            at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_tenant ON audit_events (tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_proposal ON audit_events (proposal_id)")

    # 🅱 실행 워크플로 상태 + 플랫폼 스냅샷(부분 실패 보존)
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
    op.execute("CREATE INDEX IF NOT EXISTS ix_execution_runs_approval ON execution_runs (approval_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_execution_runs_proposal ON execution_runs (proposal_id)")

    # 멱등키 선점 — key UNIQUE(PK) + INSERT ON CONFLICT DO NOTHING (게이트 #1)
    op.execute("""
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            key VARCHAR(80) PRIMARY KEY,
            approval_id VARCHAR(64) NOT NULL,
            claimed BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_idempotency_keys_approval ON idempotency_keys (approval_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
    op.execute("DROP TABLE IF EXISTS execution_runs")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP TABLE IF EXISTS approvals")
    op.execute("DROP TABLE IF EXISTS action_proposals")
