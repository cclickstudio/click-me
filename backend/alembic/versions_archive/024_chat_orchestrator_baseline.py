"""chat orchestrator baseline — repo(021)와 실 DB(024) 정합 (스탬프 기반)

레포가 인지하지 못하던 챗 오케스트레이터 KEEP 테이블을 멱등 생성해 공식화하고,
실 DB가 스탬프한 revision `024`를 레포 head로 만든다(이미 024인 DB엔 no-op).

대상(장기 KEEP) — chat_long_term_memory, chat_brand_profiles,
management_kb_documents, management_kb_eval_cases, management_kb_feedback.
제외 — Phase ② DROP 후보, checkpoints*(LangGraph 소유), management_chat_*(Phase ③ 수렴).

Revision ID: 024
Revises: 021
"""

from alembic import op

revision = "024"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        CREATE TABLE IF NOT EXISTS chat_brand_profiles (
            id uuid DEFAULT gen_random_uuid() NOT NULL,
            project_id uuid NOT NULL,
            brand_name character varying(200),
            tone character varying(100),
            target_audience character varying(200),
            product_category character varying(100),
            keywords jsonb,
            updated_at timestamp with time zone DEFAULT now() NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_long_term_memory (
            id uuid DEFAULT gen_random_uuid() NOT NULL,
            project_id uuid,
            user_id uuid,
            memory_type character varying(32) NOT NULL,
            content jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL
        );

        CREATE TABLE IF NOT EXISTS management_kb_documents (
            id uuid DEFAULT gen_random_uuid() NOT NULL,
            tenant_id character varying(64),
            visibility character varying(16) DEFAULT 'global'::character varying NOT NULL,
            source_type character varying(32) NOT NULL,
            source_url text,
            title character varying(512) NOT NULL,
            version character varying(64),
            language character varying(16) DEFAULT 'ko'::character varying NOT NULL,
            status character varying(16) DEFAULT 'active'::character varying NOT NULL,
            content_hash character varying(64),
            published_at timestamp with time zone,
            retrieved_at timestamp with time zone,
            effective_from timestamp with time zone,
            expires_at timestamp with time zone,
            verified_by character varying(128),
            metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
            created_at timestamp with time zone DEFAULT now() NOT NULL
        );

        CREATE TABLE IF NOT EXISTS management_kb_eval_cases (
            id uuid DEFAULT gen_random_uuid() NOT NULL,
            tenant_id character varying(64),
            question text NOT NULL,
            expected_tools jsonb,
            expected_points jsonb,
            expected_citations jsonb,
            expected_campaign_id character varying(64),
            expected_anomaly_type character varying(32),
            fixture_version character varying(32),
            created_at timestamp with time zone DEFAULT now() NOT NULL
        );

        CREATE TABLE IF NOT EXISTS management_kb_feedback (
            id uuid DEFAULT gen_random_uuid() NOT NULL,
            tenant_id character varying(64),
            session_id uuid,
            message_id uuid,
            question text,
            answer text,
            rating smallint,
            failure_type character varying(32),
            corrected_answer text,
            created_at timestamp with time zone DEFAULT now() NOT NULL
        );

        -- 제약·FK (멱등 — 이름으로 존재 확인 후 추가; PK 중복은 42P16이라 예외캐치 대신 사전 점검)
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_brand_profiles_pkey' AND conrelid='chat_brand_profiles'::regclass) THEN
                ALTER TABLE chat_brand_profiles ADD CONSTRAINT chat_brand_profiles_pkey PRIMARY KEY (id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_brand_profiles_project_id_key' AND conrelid='chat_brand_profiles'::regclass) THEN
                ALTER TABLE chat_brand_profiles ADD CONSTRAINT chat_brand_profiles_project_id_key UNIQUE (project_id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_long_term_memory_pkey' AND conrelid='chat_long_term_memory'::regclass) THEN
                ALTER TABLE chat_long_term_memory ADD CONSTRAINT chat_long_term_memory_pkey PRIMARY KEY (id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='management_kb_documents_pkey' AND conrelid='management_kb_documents'::regclass) THEN
                ALTER TABLE management_kb_documents ADD CONSTRAINT management_kb_documents_pkey PRIMARY KEY (id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='management_kb_eval_cases_pkey' AND conrelid='management_kb_eval_cases'::regclass) THEN
                ALTER TABLE management_kb_eval_cases ADD CONSTRAINT management_kb_eval_cases_pkey PRIMARY KEY (id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='management_kb_feedback_pkey' AND conrelid='management_kb_feedback'::regclass) THEN
                ALTER TABLE management_kb_feedback ADD CONSTRAINT management_kb_feedback_pkey PRIMARY KEY (id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_brand_profiles_project_id_fkey' AND conrelid='chat_brand_profiles'::regclass) THEN
                ALTER TABLE chat_brand_profiles ADD CONSTRAINT chat_brand_profiles_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_long_term_memory_project_id_fkey' AND conrelid='chat_long_term_memory'::regclass) THEN
                ALTER TABLE chat_long_term_memory ADD CONSTRAINT chat_long_term_memory_project_id_fkey FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='chat_long_term_memory_user_id_fkey' AND conrelid='chat_long_term_memory'::regclass) THEN
                ALTER TABLE chat_long_term_memory ADD CONSTRAINT chat_long_term_memory_user_id_fkey FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL;
            END IF;
        END $$;

        -- 인덱스 (멱등)
        CREATE INDEX IF NOT EXISTS ix_chat_ltm_project ON chat_long_term_memory USING btree (project_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS ix_kb_docs_effective ON management_kb_documents USING btree (effective_from, expires_at);
        CREATE INDEX IF NOT EXISTS ix_kb_docs_tenant_status ON management_kb_documents USING btree (tenant_id, status, source_type);
        CREATE INDEX IF NOT EXISTS ix_kb_feedback_tenant ON management_kb_feedback USING btree (tenant_id, created_at);

        -- RLS (management_kb_documents 멀티테넌트 격리)
        ALTER TABLE management_kb_documents ENABLE ROW LEVEL SECURITY;
        ALTER TABLE management_kb_documents FORCE ROW LEVEL SECURITY;
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname='tenant_isolation' AND tablename='management_kb_documents') THEN
                CREATE POLICY tenant_isolation ON management_kb_documents
                    USING ((tenant_id IS NULL) OR ((tenant_id)::text = current_setting('app.current_tenant'::text, true)))
                    WITH CHECK ((tenant_id IS NULL) OR ((tenant_id)::text = current_setting('app.current_tenant'::text, true)));
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # 베이스라인 정합 — 운영 DB에서 사용 금지(데이터 손실).
    op.execute(
        r"""
        DROP TABLE IF EXISTS management_kb_feedback CASCADE;
        DROP TABLE IF EXISTS management_kb_eval_cases CASCADE;
        DROP TABLE IF EXISTS management_kb_documents CASCADE;
        DROP TABLE IF EXISTS chat_long_term_memory CASCADE;
        DROP TABLE IF EXISTS chat_brand_profiles CASCADE;
        """
    )
