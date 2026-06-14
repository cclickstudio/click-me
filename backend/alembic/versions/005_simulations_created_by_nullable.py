"""simulations.created_by nullable (auth 미구현 단계 정합)

Revision ID: 005
Revises: 004
Create Date: 2026-06-14

현재 phase는 JWT/사용자 인증 미적용(UI만)이라 시뮬레이션 실행 시 created_by(user) 컨텍스트가 없다.
도메인 ORM은 이미 created_by nullable이며 simulations는 시뮬레이터 소유 테이블 → Neon도 완화해 정합.
auth 도입 시 NOT NULL 재적용 가능(비파괴 변경).
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE simulations ALTER COLUMN created_by DROP NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE simulations ALTER COLUMN created_by SET NOT NULL")
