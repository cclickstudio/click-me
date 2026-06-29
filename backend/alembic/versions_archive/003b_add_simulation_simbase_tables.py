"""시뮬레이터 SimBase 테이블 정합 — 빈 DB 자립 실행용

001 이 만드는 simulations·persona_responses 는 구 v2.0 스키마이고, 나머지 SimBase 5테이블
(panels·personas·ad_analyses·rubric_scores·simulation_aggregates)은 마이그레이션에 아예 없었다
(`SimBase.metadata.create_all` 로만 생성). 그 결과 빈 DB 에서 004(`ALTER personas ...`)가
`relation "personas" does not exist` 로 깨졌다.

본 리비전은 003 직후·004 직전에 끼어(004.down_revision=003→003b) 빈 DB 가 실 DB
(docs/db-erd.md introspection)와 일치하도록 시뮬 도메인을 정합한다.
- SimBase 5테이블 신설(additive 컬럼 socioeconomic/detected_objective/effective_n/
  brand_recognition_rate/weight/brand_* 는 004·006·010 이 추가하므로 여기선 제외 — baseline).
- simulations·persona_responses 를 v2.0 → SimBase 로 컬럼 변환(DROP/ADD/TYPE, 멱등).

라이브(alembic 024/025)에선 절대 실행되지 않음(현재 head 도달분만 실행). 빈 DB 전용이므로 그 시점
두 테이블은 001 이 막 만든 v2.0(빈 테이블)임이 보장된다 — NOT NULL·TYPE 변경이 안전한 이유.
id 서버 default 는 실 DB 정합을 위해 제거(ORM 가 uuid 를 파이썬에서 생성).

Revision ID: 003b
Revises: 003
Create Date: 2026-06-24
"""

from alembic import op

revision = "003b"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1) SimBase 5테이블 신설 (id 서버 default 없음 = 실 DB 정합) ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS panels (
            id                 uuid PRIMARY KEY,
            version            varchar(20) NOT NULL,
            size               integer     NOT NULL,
            seed               varchar(50) NOT NULL,
            model_version      varchar(50) NOT NULL,
            grounding_meta     jsonb       NOT NULL,
            status             varchar(20) NOT NULL DEFAULT 'BUILDING',
            built_at           timestamp,
            created_at         timestamp   NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS personas (
            id                 uuid PRIMARY KEY,
            panel_id           uuid        NOT NULL REFERENCES panels(id),
            age                integer     NOT NULL,
            gender             varchar(10) NOT NULL,
            region             varchar(50) NOT NULL,
            ocean              jsonb       NOT NULL,
            media_behavior     jsonb       NOT NULL,
            consumption_values jsonb       NOT NULL,
            profile_narrative  text        NOT NULL,
            created_at         timestamp   NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS ad_analyses (
            id                  uuid PRIMARY KEY,
            ad_id               uuid        NOT NULL REFERENCES ads(id),
            structured_analysis jsonb       NOT NULL,
            detected_industry   varchar(100),
            detected_target     varchar(100),
            detected_message    text,
            intent_mismatch     boolean     NOT NULL DEFAULT false,
            mismatch_detail     jsonb,
            model_version       varchar(50) NOT NULL,
            created_at          timestamp   NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS rubric_scores (
            id              uuid PRIMARY KEY,
            ad_analysis_id  uuid        NOT NULL REFERENCES ad_analyses(id),
            dimension       varchar(50) NOT NULL,
            score           integer     NOT NULL,
            evidence        jsonb       NOT NULL,
            created_at      timestamp   NOT NULL DEFAULT now()
        );

        CREATE TABLE IF NOT EXISTS simulation_aggregates (
            id                  uuid PRIMARY KEY,
            simulation_id       uuid         NOT NULL REFERENCES simulations(id),
            click_intent_rate   numeric(5,4) NOT NULL,
            ci_low              numeric(5,4) NOT NULL,
            ci_high             numeric(5,4) NOT NULL,
            purchase_intent_avg numeric(3,2) NOT NULL,
            trust_avg           numeric(3,2) NOT NULL,
            rejection_rate      numeric(5,4) NOT NULL,
            variance_warning    boolean      NOT NULL DEFAULT false,
            payload             jsonb        NOT NULL,
            engine_version      varchar(50)  NOT NULL,
            created_at          timestamp    NOT NULL DEFAULT now()
        );
        """
    )

    # ── 2) simulations: v2.0 → SimBase (빈 테이블 전제 → NOT NULL·TYPE 변경 안전) ──
    op.execute(
        """
        ALTER TABLE simulations DROP COLUMN IF EXISTS project_id;
        ALTER TABLE simulations DROP COLUMN IF EXISTS simulation_type;
        ALTER TABLE simulations DROP COLUMN IF EXISTS objective;
        ALTER TABLE simulations DROP COLUMN IF EXISTS persona_count;
        ALTER TABLE simulations DROP COLUMN IF EXISTS persona_config;
        ALTER TABLE simulations DROP COLUMN IF EXISTS results_summary;
        ALTER TABLE simulations DROP COLUMN IF EXISTS llm_cost_usd;
        ALTER TABLE simulations DROP COLUMN IF EXISTS sqs_message_id;
        ALTER TABLE simulations DROP COLUMN IF EXISTS error_message;

        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS ad_analysis_id    uuid        NOT NULL;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS panel_id          uuid;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS organization_id   uuid        NOT NULL;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS target_filter     jsonb;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS target_mode       varchar(10) NOT NULL DEFAULT 'AUTO';
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS sample_size       integer     NOT NULL;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS qa_passed_count   integer;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS low_sample_warning boolean    NOT NULL DEFAULT false;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS model_version     varchar(50) NOT NULL DEFAULT 'gpt-4o-mini';
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS error_detail      jsonb;
        ALTER TABLE simulations ADD COLUMN IF NOT EXISTS deleted_at        timestamp;

        -- status: enum simulation_status → varchar(20) DEFAULT 'QUEUED'
        ALTER TABLE simulations ALTER COLUMN status DROP DEFAULT;
        ALTER TABLE simulations ALTER COLUMN status TYPE varchar(20) USING status::text;
        ALTER TABLE simulations ALTER COLUMN status SET DEFAULT 'QUEUED';

        -- timestamptz → timestamp(실 DB 정합), id 서버 default 제거
        ALTER TABLE simulations ALTER COLUMN started_at   TYPE timestamp;
        ALTER TABLE simulations ALTER COLUMN completed_at TYPE timestamp;
        ALTER TABLE simulations ALTER COLUMN created_at   TYPE timestamp;
        ALTER TABLE simulations ALTER COLUMN id DROP DEFAULT;
        """
    )

    # ── 3) persona_responses: v2.0 → SimBase (weight=004, brand_*=010 추가분은 제외) ──
    op.execute(
        """
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS producer_id;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS segment;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS ocean;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS persona_attributes;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS free_text_reaction;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS exposure_output;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS deliberation_output;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS signals;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS confidence;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS is_outlier;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS anchor_version;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS embedding_model;
        ALTER TABLE persona_responses DROP COLUMN IF EXISTS response_time_ms;

        ALTER TABLE persona_responses ALTER COLUMN persona_id TYPE uuid USING persona_id::uuid;

        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS exposure_context    varchar(50);
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS aisas               jsonb       NOT NULL;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS drop_stage          varchar(20);
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS drop_reason_tag     varchar(50);
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS purchase_intent     integer     NOT NULL;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS trust               integer     NOT NULL;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS rejected            boolean     NOT NULL DEFAULT false;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS rejection_reason_tag varchar(50);
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS emotion_tag         varchar(50) NOT NULL;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS perceived_message   text;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS perceived_target    varchar(100);
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS utterance           text;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS qa_passed           boolean     NOT NULL;
        ALTER TABLE persona_responses ADD COLUMN IF NOT EXISTS qa_fail_reason      varchar(100);

        ALTER TABLE persona_responses ALTER COLUMN created_at TYPE timestamp;
        ALTER TABLE persona_responses ALTER COLUMN id DROP DEFAULT;
        """
    )

    # ── 4) 신규 FK (멱등 — conname 존재 점검 후 추가, 024 패턴) ──
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='simulations_ad_analysis_id_fkey' AND conrelid='simulations'::regclass) THEN
                ALTER TABLE simulations ADD CONSTRAINT simulations_ad_analysis_id_fkey FOREIGN KEY (ad_analysis_id) REFERENCES ad_analyses(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='simulations_panel_id_fkey' AND conrelid='simulations'::regclass) THEN
                ALTER TABLE simulations ADD CONSTRAINT simulations_panel_id_fkey FOREIGN KEY (panel_id) REFERENCES panels(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='simulations_organization_id_fkey' AND conrelid='simulations'::regclass) THEN
                ALTER TABLE simulations ADD CONSTRAINT simulations_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES organizations(id);
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='persona_responses_persona_id_fkey' AND conrelid='persona_responses'::regclass) THEN
                ALTER TABLE persona_responses ADD CONSTRAINT persona_responses_persona_id_fkey FOREIGN KEY (persona_id) REFERENCES personas(id);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # SimBase 5테이블만 회수. simulations·persona_responses 의 v2.0 복원은 비대상(빈 DB 전용 리비전).
    op.execute(
        """
        DROP TABLE IF EXISTS simulation_aggregates CASCADE;
        DROP TABLE IF EXISTS rubric_scores CASCADE;
        DROP TABLE IF EXISTS ad_analyses CASCADE;
        DROP TABLE IF EXISTS personas CASCADE;
        DROP TABLE IF EXISTS panels CASCADE;
        """
    )
