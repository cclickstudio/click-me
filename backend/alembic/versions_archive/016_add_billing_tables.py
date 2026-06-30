"""add billing tables — 크레딧 충전 주문·원장 영속

Revision ID: 016
Revises: 015
Create Date: 2026-06-21

core/models.py의 PaymentOrderRow·CreditLedgerRow와 1:1. 인메모리 Repository를 DB로 교체해
서버 재시작 후에도 충전 잔액·집행 차감 이력이 유지된다. credit_ledger는 append-only.
"""

from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS payment_orders (
            order_id VARCHAR(64) PRIMARY KEY,
            org_id VARCHAR(64) NOT NULL,
            amount_krw INTEGER NOT NULL,
            status VARCHAR(16) NOT NULL,
            payment_key VARCHAR(128),
            raw_response JSONB,
            cancel_response JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            approved_at TIMESTAMPTZ,
            canceled_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_payment_orders_org_id ON payment_orders (org_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id BIGSERIAL PRIMARY KEY,
            org_id VARCHAR(64) NOT NULL,
            delta_krw INTEGER NOT NULL,
            balance_after_krw INTEGER NOT NULL,
            reason VARCHAR(16) NOT NULL,
            ref_id VARCHAR(128) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_credit_ledger_org_id ON credit_ledger (org_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS credit_ledger")
    op.execute("DROP TABLE IF EXISTS payment_orders")
