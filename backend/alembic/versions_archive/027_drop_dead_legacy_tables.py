"""drop dead/legacy tables — audit_logs/user_settings + orphan KB·chat 잔재 4종

Revision ID: 027
Revises: 026
Create Date: 2026-06-26

코드 참조가 0인 죽은 테이블을 정리한다(팀 합의 후).
- audit_logs: 초기(001) 잔재, audit_events가 대체.
- user_settings: 초기(001) 잔재, 미구현.
- rag_chunks / generator_kb_chunks / chat_long_term_memory / chat_brand_profiles:
  ORM·마이그레이션·코드 어디에도 없는 orphan(과거 create_all 등으로 남은 0행 테이블).

⚠️ diagnoses는 projects.py 캐스케이드 삭제가 사용하므로 제외(드롭 금지).
downgrade는 스키마가 명확한 audit_logs·user_settings(001 기준)만 복원한다. orphan 4종은
정의 출처가 없어 복원 대상이 아니다(forward-only).

⚠️ 🤝 DB 스키마 변경 — down_revision(head=026) 합의 필요(CLAUDE.md 협업 규칙). 일부는 타 도메인
(generator·chat) 테이블이라 합의 후 제거.
"""

from alembic import op

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit_logs")
    op.execute("DROP TABLE IF EXISTS user_settings")
    op.execute("DROP TABLE IF EXISTS rag_chunks")
    op.execute("DROP TABLE IF EXISTS generator_kb_chunks")
    op.execute("DROP TABLE IF EXISTS chat_long_term_memory")
    op.execute("DROP TABLE IF EXISTS chat_brand_profiles")


def downgrade() -> None:
    # 001_initial_schema 기준 — 스키마가 명확한 2종만 복원(orphan 4종은 출처 부재로 미복원).
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            theme VARCHAR(10) NOT NULL DEFAULT 'light',
            notifications JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(100) NOT NULL,
            resource VARCHAR(50),
            resource_id UUID,
            metadata JSONB,
            ip_address VARCHAR(45),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
