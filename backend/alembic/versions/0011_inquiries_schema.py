# 고객 문의 테이블 재정의 — 폼 계약(title/content/contact_email) 정합 + 해결 상태(is_resolved) 추가
"""redefine inquiries table to title/content/contact_email + is_resolved

Revision ID: 0011_inquiries_schema
Revises: 0010_management_approval_records
Create Date: 2026-07-08

기존 inquiries(name/email/message)는 라우터가 인메모리 스텁이라 실사용된 적 없고 빈 테이블.
프론트/스키마 계약(title/content/contact_email)에 맞춰 재정의하고, 관리자 조회·해결용
is_resolved/resolved_at를 추가한다. 빈 테이블이라 DROP+CREATE로 재정의(데이터 손실 없음).
빈 DB는 create_all이 ORM(Inquiry)대로 만들고, 아래 멱등 가드가 no-op이 된다. 재실행 안전.
"""

from alembic import op

revision = "0011_inquiries_schema"
down_revision = "0010_management_approval_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 구 스키마(name/email/message) 빈 테이블 → 신 스키마로 재생성.
    op.execute("DROP TABLE IF EXISTS inquiries")
    op.execute(
        """
        CREATE TABLE inquiries (
            id UUID PRIMARY KEY,
            title VARCHAR(300) NOT NULL,
            content TEXT NOT NULL,
            contact_email VARCHAR(255),
            is_resolved BOOLEAN NOT NULL DEFAULT false,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_inquiries_created_at ON inquiries (created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inquiries")
