# 현재 ORM 전체 스키마 baseline — 엉킨 중복 revision(29개) 정리(squash). create_all + 수동 DDL 보강.
"""squash baseline — current ORM schema (core.Base 41 + SimBase 7 = 48 tables)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-29

기존 001~029(중복 id 다수)와 후속 0002(kb 임베딩 1536)·0003(chat 스키마 보정)·
0002_execution_history(실행 히스토리 — ORM에 이미 포함돼 create_all이 생성)를 단일
baseline으로 흡수·대체한다. 스키마 진실은 ORM(core.models + domain.simulation.models)이며,
빈 DB는 이 한 파일로 현재 스키마 전체를 재현하고, 기존 실 DB는 stamp만 한다.

create_all이 재현하지 못하는 실 DB 객체(옛 수동 마이그 유산)는 뒤쪽 수동 DDL 섹션이 보강한다.
① ORM 미매핑 컬럼(ad_generations.deleted_at, management_kb_chunks.search_vector 생성열)
② 크로스베이스 FK(SimBase↔core — metadata 분리로 ORM 선언 불가)
③ ORM 미선언 인덱스(유니크 제약 포함).
전부 멱등(IF NOT EXISTS·가드) — 이미 있는 객체는 건너뛴다.
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# 크로스베이스 FK — (제약명, 테이블, 컬럼, 참조테이블, ON DELETE). ORM은 CoreBase·SimBase의
# metadata가 분리돼 상호 FK를 선언할 수 없어 DB 레벨로만 유지한다(실 DB와 동일 구성).
_CROSS_BASE_FKS = [
    ("fk_ad_analyses_ad", "ad_analyses", "ad_id", "ads", "NO ACTION"),
    ("fk_persona_debates_simulation", "persona_debates", "simulation_id", "simulations", "CASCADE"),
    ("fk_persona_responses_persona", "persona_responses", "persona_id", "personas", "NO ACTION"),
    (
        "fk_persona_responses_simulation",
        "persona_responses",
        "simulation_id",
        "simulations",
        "NO ACTION",
    ),
    ("fk_personas_panel", "personas", "panel_id", "panels", "NO ACTION"),
    ("fk_rubric_scores_ad_analysis", "rubric_scores", "ad_analysis_id", "ad_analyses", "NO ACTION"),
    (
        "fk_simulation_aggregates_simulation",
        "simulation_aggregates",
        "simulation_id",
        "simulations",
        "NO ACTION",
    ),
    ("fk_simulations_ad_analysis", "simulations", "ad_analysis_id", "ad_analyses", "NO ACTION"),
    ("fk_simulations_ad", "simulations", "ad_id", "ads", "NO ACTION"),
    ("fk_simulations_created_by", "simulations", "created_by", "users", "NO ACTION"),
    ("fk_simulations_organization", "simulations", "organization_id", "organizations", "NO ACTION"),
    ("fk_simulations_panel", "simulations", "panel_id", "panels", "NO ACTION"),
]

# ORM 미선언 인덱스 — 옛 수동 마이그가 만들던 것 중 ORM(create_all)이 같은 컬럼 조합으로
# 만들어 주지 않는 것만(기능 중복분은 제외). (UNIQUE 여부, 인덱스명, 테이블, 컬럼식)
_EXTRA_INDEXES = [
    (True, "uq_org_member", "organization_members", "(organization_id, user_id)"),
    (True, "uq_response", "persona_responses", "(simulation_id, persona_id)"),
    (True, "uq_rubric", "rubric_scores", "(ad_analysis_id, dimension)"),
    (False, "idx_ad_campaign_logs_generation", "ad_campaign_logs", "(generation_id)"),
    (
        False,
        "idx_ad_generation_candidates_generation",
        "ad_generation_candidates",
        "(generation_id)",
    ),
    (False, "idx_ad_generations_deleted_at", "ad_generations", "(deleted_at)"),
    (False, "idx_projects_deleted_at", "projects", "(deleted_at)"),
    (False, "idx_projects_team_id", "projects", "(team_id)"),
    (False, "idx_simulations_deleted_at", "simulations", "(deleted_at)"),
    (False, "idx_teams_org", "teams", "(organization_id)"),
    (False, "idx_users_team", "users", "(team_id)"),
    (False, "ix_brand_kits_org", "brand_kits", "(organization_id)"),
    (False, "ix_meta_connections_status", "management_meta_connections", "(status)"),
    (
        False,
        "ix_kb_docs_tenant_status",
        "management_kb_documents",
        "(tenant_id, status, source_type)",
    ),
    (False, "ix_kb_docs_effective", "management_kb_documents", "(effective_from, expires_at)"),
    (False, "ix_kb_chunks_document", "management_kb_chunks", "(document_id, chunk_index)"),
    (False, "ix_kb_chunks_tenant", "management_kb_chunks", "(tenant_id)"),
    (False, "ix_chat_sessions_thread", "management_chat_sessions", "(thread_id)"),
    (False, "ix_chat_sessions_tenant", "management_chat_sessions", "(tenant_id, last_active_at)"),
    (False, "ix_chat_messages_session", "management_chat_messages", "(session_id, created_at)"),
    (False, "ix_agent_runs_thread", "management_agent_runs", "(thread_id)"),
    (False, "ix_kb_feedback_tenant", "management_kb_feedback", "(tenant_id, created_at)"),
    # ix_user_memory_scope(management_user_memory)는 0006 drop과 함께 제거 —
    # ORM에서 테이블이 빠져 create_all이 안 만들므로 여기 있으면 신규 DB에서 실패한다.
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # chat_messages.role 은 create_type=False 인 네이티브 ENUM이라 create_all이 만들지 않는다.
    # 테이블보다 먼저 멱등 생성(CREATE TYPE에는 IF NOT EXISTS가 없어 DO 블록으로 가드).
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'chat_role') THEN
                CREATE TYPE chat_role AS ENUM ('user', 'assistant');
            END IF;
        END $$;
        """
    )

    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415
    from domain.simulation.models import SimBase  # noqa: PLC0415

    # core 먼저(ads/projects 등) → SimBase(core를 FK 참조) 순으로 생성.
    CoreBase.metadata.create_all(bind)
    SimBase.metadata.create_all(bind)

    # users.password_hash는 인증 Cognito 단일화로 ORM에서 제거됨(비번은 Cognito가 단일 관리).
    # create_all은 ORM을 따르므로 빈 DB엔 처음부터 없다. 이전 스키마(컬럼 존재)인 DB를
    # baseline으로 올릴 때만 대비해 멱등 drop — 있으면 제거, 없으면 no-op.
    insp = sa.inspect(bind)
    if any(c["name"] == "password_hash" for c in insp.get_columns("users")):
        op.drop_column("users", "password_hash")

    # ── 수동 DDL 보강 — create_all이 재현하지 못하는 실 DB 객체(전부 멱등) ──

    # ① ORM 미매핑 컬럼. deleted_at은 소프트삭제(raw SQL로만 접근 — projects·dashboard 라우터),
    #    search_vector는 키워드 검색용 tsvector 생성열(management retriever가 사용).
    op.execute("ALTER TABLE ad_generations ADD COLUMN IF NOT EXISTS deleted_at timestamp")
    op.execute(
        """
        ALTER TABLE management_kb_chunks ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk, ''))) STORED
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_search "
        "ON management_kb_chunks USING GIN (search_vector)"
    )

    # ② 크로스베이스 FK — 제약명으로 가드(ADD CONSTRAINT에는 IF NOT EXISTS가 없음).
    for name, table, col, ref, on_delete in _CROSS_BASE_FKS:
        op.execute(
            f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = '{name}') THEN
                    ALTER TABLE {table} ADD CONSTRAINT {name}
                        FOREIGN KEY ({col}) REFERENCES {ref} (id) ON DELETE {on_delete};
                END IF;
            END $$;
            """
        )

    # ③ ORM 미선언 인덱스(유니크 제약 포함).
    for unique, name, table, cols in _EXTRA_INDEXES:
        kind = "UNIQUE INDEX" if unique else "INDEX"
        op.execute(f"CREATE {kind} IF NOT EXISTS {name} ON {table} {cols}")


def downgrade() -> None:
    bind = op.get_bind()
    from core.models import Base as CoreBase  # noqa: PLC0415
    from domain.simulation.models import SimBase  # noqa: PLC0415

    # 크로스베이스 FK가 SimBase drop을 막지 않도록 먼저 해제. 수동 컬럼·인덱스는 테이블과 함께 삭제.
    for name, table, _col, _ref, _od in reversed(_CROSS_BASE_FKS):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    SimBase.metadata.drop_all(bind)
    CoreBase.metadata.drop_all(bind)
    op.execute("DROP TYPE IF EXISTS chat_role")
