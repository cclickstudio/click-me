"""auth 개편 — users.email→login_id rename + 신규 컬럼 + teams 테이블

Revision ID: 007
Revises: 006
Create Date: 2026-06-15

dev 의 core/models.py 변경(로그인 아이디화·계정 발급·팀 관리)에 대응하는 마이그레이션.
ORM 만 바뀌고 마이그레이션이 누락돼 있어 DB(Neon, alembic 006)와 드리프트가 발생 → 본 리비전으로 정합.

변경:
- teams 테이블 신규 (users.team_id FK 부모 — 먼저 생성)
- users.email → login_id 로 rename (데이터·UNIQUE 보존)
- users 신규 컬럼: must_change_password / team_id(FK→teams) / phone_num / user_email

⚠️ 작성자(인증/dev) 검토 필요 — 특히 email→login_id rename 은 인증·로그인에 직접 영향.
   기존 email 값을 login_id 로 그대로 이전하는 정책을 전제로 한다(별도 user_email 은 연락용).
멱등(IF NOT EXISTS / 가드 DO 블록) — 재실행·부분적용 안전.
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) teams (users.team_id FK 부모) — 먼저 생성. 001 컨벤션(gen_random_uuid·TIMESTAMPTZ) 준수.
    op.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            name VARCHAR(100) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # 2) users.email → login_id (데이터·UNIQUE 인덱스 보존). email 있고 login_id 없을 때만.
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='users' AND column_name='email'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='users' AND column_name='login_id'
            ) THEN
                ALTER TABLE users RENAME COLUMN email TO login_id;
            END IF;
        END $$;
    """)

    # 3) users 신규 컬럼 (additive)
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "must_change_password BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "team_id UUID REFERENCES teams(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_num VARCHAR(30)")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS user_email VARCHAR(255)")


def downgrade() -> None:
    # 역순 — team_id(FK) 먼저 제거 후 teams 드롭, login_id → email 복원.
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS user_email")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS phone_num")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS team_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS must_change_password")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='users' AND column_name='login_id'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name='users' AND column_name='email'
            ) THEN
                ALTER TABLE users RENAME COLUMN login_id TO email;
            END IF;
        END $$;
    """)
    op.execute("DROP TABLE IF EXISTS teams")
