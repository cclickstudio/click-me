"""persist idempotency result + align audit_events to AuditEvent (B-1)

Revision ID: 009
Revises: 008
Create Date: 2026-06-16

⚠️ 리비전 재정렬(2026-06-18) — 본래 007/006으로 선언돼 auth 체인의 007과 충돌했다.
management 008(add_management_tables) 뒤에 이어지도록 009/008로 재배치한다.
(audit_events·idempotency_keys는 008에서 생성되므로 반드시 008 다음이어야 함.)

멱등 결과 replay(게이트 #1)용 idempotency_keys.result + 감사 영속화를 위해
audit_events 컬럼을 코드의 AuditEvent(category·run_id·event_id·payload)와 정합.
기존 테이블은 인메모리만 쓰여 데이터가 없으므로 ALTER 안전.
"""

from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 멱등 결과 replay — 같은 키 재제출 시 저장된 ActionResult를 그대로 반환
    op.execute("ALTER TABLE idempotency_keys ADD COLUMN IF NOT EXISTS result JSONB")

    # audit_events ↔ 코드 AuditEvent 정합
    op.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS event_id VARCHAR(64)")
    op.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS category VARCHAR(64)")
    op.execute("ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS run_id VARCHAR(64)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_events_event ON audit_events (event_id)")
    # 코드가 생성하지 않는 컬럼은 NOT NULL 완화
    op.execute("ALTER TABLE audit_events ALTER COLUMN stage DROP NOT NULL")
    op.execute("ALTER TABLE audit_events ALTER COLUMN outcome DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE audit_events ALTER COLUMN outcome SET NOT NULL")
    op.execute("ALTER TABLE audit_events ALTER COLUMN stage SET NOT NULL")
    op.execute("DROP INDEX IF EXISTS ix_audit_events_event")
    op.execute("ALTER TABLE audit_events DROP COLUMN IF EXISTS run_id")
    op.execute("ALTER TABLE audit_events DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE audit_events DROP COLUMN IF EXISTS event_id")
    op.execute("ALTER TABLE idempotency_keys DROP COLUMN IF EXISTS result")
