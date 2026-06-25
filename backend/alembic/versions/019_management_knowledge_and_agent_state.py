"""매니지먼트 지식·에이전트 상태 스키마 — 4개 층 기반 (additive)

Revision ID: 019
Revises: 018
Create Date: 2026-06-23

에이전틱 RAG를 위해 KB를 문서/청크로 분리(테넌트·버전·출처·유효기간·키워드검색),
채팅·에이전트 실행 상태, 평가·피드백을 관계형으로 적재한다. 전부 additive(IF NOT EXISTS)라
기존 management_kb_chunks 데이터·운영을 깨지 않는다. 실시간 수치는 여전히 live tool로 읽는다.
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── 1층: RAG 지식 문서 (청크의 부모) ──────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_kb_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(64),                       -- NULL = 공통(global) 지식
            visibility VARCHAR(16) NOT NULL DEFAULT 'global',   -- global|tenant|project
            source_type VARCHAR(32) NOT NULL,           -- meta_official|internal_policy|benchmark|playbook
            source_url TEXT,
            title VARCHAR(512) NOT NULL,
            version VARCHAR(64),
            language VARCHAR(16) NOT NULL DEFAULT 'ko',
            status VARCHAR(16) NOT NULL DEFAULT 'active',-- draft|active|deprecated
            content_hash VARCHAR(64),
            published_at TIMESTAMPTZ,
            retrieved_at TIMESTAMPTZ,
            effective_from TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            verified_by VARCHAR(128),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_docs_tenant_status "
        "ON management_kb_documents (tenant_id, status, source_type)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_docs_effective "
        "ON management_kb_documents (effective_from, expires_at)"
    )

    # ── management_kb_chunks 확장: 문서 연결 + 메타 + 키워드검색 (기존 컬럼 유지) ──
    op.execute("""
        ALTER TABLE management_kb_chunks
            ADD COLUMN IF NOT EXISTS document_id UUID
                REFERENCES management_kb_documents(id) ON DELETE CASCADE,
            ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64),
            ADD COLUMN IF NOT EXISTS chunk_index INTEGER,
            ADD COLUMN IF NOT EXISTS heading_path TEXT,
            ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64),
            ADD COLUMN IF NOT EXISTS token_count INTEGER,
            ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(64),
            ADD COLUMN IF NOT EXISTS embedding_dimensions INTEGER
    """)
    # 키워드 검색(GIN) — 한국어는 별도 사전이 없어 'simple'로 토큰 그대로 색인.
    # ROAS·PENDING_REVIEW·BID_LOSS 같은 정확 용어 매칭에 강함. STORED 생성열로 자동 유지.
    op.execute("""
        ALTER TABLE management_kb_chunks
            ADD COLUMN IF NOT EXISTS search_vector tsvector
            GENERATED ALWAYS AS (to_tsvector('simple', coalesce(chunk, ''))) STORED
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_search "
        "ON management_kb_chunks USING GIN (search_vector)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_chunks_document "
        "ON management_kb_chunks (document_id, chunk_index)"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_kb_chunks_tenant ON management_kb_chunks (tenant_id)")

    # ── 3층: 채팅 세션 + 메시지 (멀티턴·관측) ──────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_chat_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(64),
            user_id VARCHAR(64),
            project_id VARCHAR(64),
            thread_id VARCHAR(128) NOT NULL,
            campaign_id VARCHAR(64),
            ad_id VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_active_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_thread ON management_chat_sessions (thread_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_sessions_tenant "
        "ON management_chat_sessions (tenant_id, last_active_at)"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_chat_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID REFERENCES management_chat_sessions(id) ON DELETE CASCADE,
            thread_id VARCHAR(128),
            role VARCHAR(16) NOT NULL,                  -- user|assistant|tool
            content TEXT,
            model VARCHAR(64),
            prompt_version VARCHAR(64),
            tokens_in INTEGER,
            tokens_out INTEGER,
            latency_ms INTEGER,
            campaign_id VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chat_messages_session "
        "ON management_chat_messages (session_id, created_at)"
    )

    # ── 3층: 에이전트 실행 이력 (도구·검색·인용·HITL) ──────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_agent_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            session_id UUID REFERENCES management_chat_sessions(id) ON DELETE CASCADE,
            thread_id VARCHAR(128),
            message_id UUID,
            tools_used JSONB NOT NULL DEFAULT '[]'::jsonb,        -- [{tool,input,result_hash}]
            retrieved_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [{chunk_id,score}]
            citations JSONB NOT NULL DEFAULT '[]'::jsonb,
            steps INTEGER,
            error TEXT,
            interrupt_state JSONB,
            suggested_action JSONB,
            approved_by VARCHAR(64),
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_runs_thread ON management_agent_runs (thread_id)"
    )

    # ── 4층: 평가셋 + 피드백 (RAG 품질 회귀) ───────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_kb_eval_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(64),
            question TEXT NOT NULL,
            expected_tools JSONB,
            expected_points JSONB,
            expected_citations JSONB,
            expected_campaign_id VARCHAR(64),
            expected_anomaly_type VARCHAR(32),
            fixture_version VARCHAR(32),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS management_kb_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id VARCHAR(64),
            session_id UUID,
            message_id UUID,
            question TEXT,
            answer TEXT,
            rating SMALLINT,                            -- 1 like / -1 dislike
            failure_type VARCHAR(32),                   -- wrong_tool|stale_doc|cross_tenant|
                                                        -- hallucinated_number|missing_citation|over_action
            corrected_answer TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_kb_feedback_tenant "
        "ON management_kb_feedback (tenant_id, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS management_kb_feedback")
    op.execute("DROP TABLE IF EXISTS management_kb_eval_cases")
    op.execute("DROP TABLE IF EXISTS management_agent_runs")
    op.execute("DROP TABLE IF EXISTS management_chat_messages")
    op.execute("DROP TABLE IF EXISTS management_chat_sessions")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_search")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_document")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_tenant")
    op.execute("""
        ALTER TABLE management_kb_chunks
            DROP COLUMN IF EXISTS search_vector,
            DROP COLUMN IF EXISTS embedding_dimensions,
            DROP COLUMN IF EXISTS embedding_model,
            DROP COLUMN IF EXISTS token_count,
            DROP COLUMN IF EXISTS content_hash,
            DROP COLUMN IF EXISTS heading_path,
            DROP COLUMN IF EXISTS chunk_index,
            DROP COLUMN IF EXISTS tenant_id,
            DROP COLUMN IF EXISTS document_id
    """)
    op.execute("DROP TABLE IF EXISTS management_kb_documents")
