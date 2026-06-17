"""add persona debate tables (persona_debates / participants / utterances)

Revision ID: 007b
Revises: 007
Create Date: 2026-06-16

시뮬레이터 4-1 페르소나 토론 — simulations 1:N 토론 3테이블 신설(db-schema v3.1).
비파괴(additive, IF NOT EXISTS)만. 기존 debate_* 3테이블 DROP은 별도(0행 확인 후 수기/후속 마이그레이션).
persona_id는 더미 문자열·실 UUID 양쪽 수용 위해 VARCHAR(50).
"""

from alembic import op

revision = "007b"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS persona_debates (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            simulation_id UUID        NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
            topic         TEXT,
            rounds_run    INTEGER,
            stop_reason   VARCHAR(20),
            judge_model   VARCHAR(50),
            engines       JSONB,
            judge_log     JSONB,
            final         JSONB,
            status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_persona_debates_sim ON persona_debates(simulation_id)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS persona_debate_participants (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            debate_id       UUID        NOT NULL REFERENCES persona_debates(id) ON DELETE CASCADE,
            persona_id      VARCHAR(50) NOT NULL,
            persona_name    VARCHAR(50),
            persona_profile TEXT,
            role            VARCHAR(20),
            engine          VARCHAR(20),
            UNIQUE (debate_id, persona_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS persona_debate_utterances (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            debate_id      UUID    NOT NULL REFERENCES persona_debates(id) ON DELETE CASCADE,
            participant_id UUID    REFERENCES persona_debate_participants(id) ON DELETE CASCADE,
            round          INTEGER NOT NULL,
            phase          VARCHAR(10),
            stance         VARCHAR(10),
            text           TEXT,
            reason         TEXT,
            lever          TEXT,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_persona_debate_utt_debate "
        "ON persona_debate_utterances(debate_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS persona_debate_utterances")
    op.execute("DROP TABLE IF EXISTS persona_debate_participants")
    op.execute("DROP TABLE IF EXISTS persona_debates")
