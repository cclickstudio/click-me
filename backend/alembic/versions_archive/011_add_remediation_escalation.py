"""add remediation_escalations table — 시간축 에스컬레이션 사다리 상태

Revision ID: 008_mgmt_escalation
Revises: 007 (management 라인 — 007_persist_idempotency_audit)
Create Date: 2026-06-17

core/models.py의 RemediationEscalationRow와 1:1. 캠페인당 active 1건의 사다리 진행 상태.
컬럼 규칙: 타임스탬프=TIMESTAMPTZ / 유연 페이로드(JSONB) / enum=VARCHAR + 앱 레벨 검증.

⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(라인 head) 합의 필요. 리포에 006/007 중복
revision id가 있어(병렬 브랜치), 통합 시 체인 정리가 함께 필요하다(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
    # 캠페인당 active 사다리는 1건 — 부분 UNIQUE로 강제 (앱 레벨 보강)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_remediation_escalations_active "
        "ON remediation_escalations (tenant_id, campaign_id) WHERE status = 'active'"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS remediation_escalations")
