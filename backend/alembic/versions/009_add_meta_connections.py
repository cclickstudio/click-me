"""add meta_connections table — 테넌트별 Meta OAuth 연결(암호화 토큰)

Revision ID: 009_meta_connections
Revises: 008_mgmt_escalation
Create Date: 2026-06-18

core/models.py의 MetaConnection과 1:1. 외부 광고주가 자기 Meta 자산을 연결하면 org당 1건.
access_token_enc는 AES-256-GCM 암호문(평문 토큰 저장 금지 — CLAUDE.md 보안 규칙).
컬럼 규칙: 타임스탬프=TIMESTAMPTZ / scopes=JSONB / enum=VARCHAR + 앱 레벨 검증.

⚠️ 🤝 DB 스키마 변경 — 머지 전 down_revision(라인 head) 합의 필요(CLAUDE.md 협업 규칙).
"""

from alembic import op

revision = "009_meta_connections"
down_revision = "008_mgmt_escalation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS meta_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL UNIQUE
                REFERENCES organizations(id) ON DELETE CASCADE,
            access_token_enc TEXT NOT NULL,
            ad_account_id VARCHAR(64),
            page_id VARCHAR(64),
            ig_user_id VARCHAR(64),
            scopes JSONB,
            token_expires_at TIMESTAMPTZ,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_meta_connections_status ON meta_connections (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meta_connections")
