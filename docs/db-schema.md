# ClickMe DB Schema

| Version | v2.0 |
|---|---|
| Date | 2026-06-09 |
| DB | NeonDB (PostgreSQL + pgvector) |
| Migration | Alembic |

---

## v1.0 → v2.0 Key Changes

| Item | Change |
|---|---|
| `persona_responses.signals` | JSONB → distribution structure |
| `persona_responses` new columns | `ocean`, `free_text_reaction`, `exposure_output`, `deliberation_output` added |
| `simulations` | `persona_config` JSONB includes OCEAN settings |
| `inquiries` table | New table added (customer inquiries) |
| `ad_generations` / `ad_generation_candidates` / `ad_publish_logs` | Generator pipeline tables (migration 003) |
| `calibration_data` | Not implemented (TBD). Table definition retained. |
| `simulation_type` enum | `'survey'` removal pending (open issue) |
| `refresh_tokens` | Phase 1 has no auth. Table definition retained. |

---

## Full Schema

```sql
-- ============================================================
-- ClickMe DB Schema v2.0
-- NeonDB (PostgreSQL + pgvector)
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- ENUM types
-- ============================================================

CREATE TYPE user_role         AS ENUM ('admin', 'user');
CREATE TYPE project_status    AS ENUM ('active', 'archived');
CREATE TYPE project_member_role AS ENUM ('owner', 'editor', 'viewer');
CREATE TYPE ad_input_type     AS ENUM ('image', 'text', 'video', 'url');
CREATE TYPE ad_status         AS ENUM ('pending', 'analyzing', 'completed', 'failed');
CREATE TYPE simulation_type   AS ENUM ('ad_reaction');  -- v2.0: survey removed
CREATE TYPE simulation_status AS ENUM ('pending', 'running', 'completed', 'failed');
CREATE TYPE chat_role         AS ENUM ('user', 'assistant');
CREATE TYPE plan_type         AS ENUM ('free', 'professional', 'enterprise');
CREATE TYPE campaign_objective AS ENUM ('awareness', 'conversion');

-- ============================================================
-- Organizations (billing unit)
-- ============================================================

CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(200) NOT NULL,
    plan_type   plan_type NOT NULL DEFAULT 'free',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Users
-- Created by admin. No social login.
-- Phase 1: password_hash unused (UI auth only)
-- ============================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255),               -- used in Phase 2
    name            VARCHAR(100) NOT NULL,
    role            user_role NOT NULL DEFAULT 'user',
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Refresh Tokens (used in Phase 2)
-- ============================================================

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  VARCHAR(255) NOT NULL UNIQUE,
    expires_at  TIMESTAMPTZ NOT NULL,
    revoked     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Projects (campaign unit)
-- ============================================================

CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users(id),
    name            VARCHAR(200) NOT NULL,
    description     TEXT,
    status          project_status NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Project Members (team management [7.8])
-- ============================================================

CREATE TABLE project_members (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        project_member_role NOT NULL DEFAULT 'viewer',
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, user_id)
);

-- ============================================================
-- Ads (uploaded ad creatives)
-- ============================================================

CREATE TABLE ads (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_by          UUID NOT NULL REFERENCES users(id),
    name                VARCHAR(200) NOT NULL,
    input_type          ad_input_type NOT NULL,
    storage_path        TEXT,
    storage_url         TEXT,
    text_content        JSONB,
    source_url          TEXT,
    analysis_status     ad_status NOT NULL DEFAULT 'pending',
    analysis_result     JSONB,
    analysis_confidence FLOAT CHECK (analysis_confidence >= 0.0 AND analysis_confidence <= 1.0),
    analysis_error      TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Persona Templates (RAG, pgvector)
-- ============================================================

CREATE TABLE persona_templates (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100),
    cluster_id  VARCHAR(50),
    attributes  JSONB NOT NULL,
    -- v2.0: includes OCEAN
    -- attributes structure:
    -- {
    --   "ocean": {"openness": 0.7, "conscientiousness": 0.6, ...},
    --   "demographics": {...},
    --   "behaviors": {...},
    --   "narrative": {...}
    -- }
    embedding   vector(1536),
    is_public   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Simulations
-- ============================================================

CREATE TABLE simulations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    ad_id           UUID NOT NULL REFERENCES ads(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users(id),
    simulation_type simulation_type NOT NULL DEFAULT 'ad_reaction',
    objective       campaign_objective NOT NULL DEFAULT 'conversion',
    status          simulation_status NOT NULL DEFAULT 'pending',
    persona_count   INTEGER NOT NULL DEFAULT 20,
    persona_config  JSONB,
    -- persona_config structure:
    -- {
    --   "ocean_cv_min": 0.3,
    --   "segment_distribution": {...},
    --   "anchor_version": "v1.0"
    -- }
    requested_count INTEGER,
    received_count  INTEGER,
    sample_size     INTEGER,
    results_summary JSONB,          -- P0/P1 aggregated result snapshot
    llm_cost_usd    FLOAT DEFAULT 0.0,
    sqs_message_id  VARCHAR(100),   -- SQS tracking
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Persona Responses (v2.0 extended)
-- ============================================================

CREATE TABLE persona_responses (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id        UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    persona_id           VARCHAR(50) NOT NULL,
    producer_id          VARCHAR(100),
    segment              VARCHAR(100),
    -- v2.0 new: OCEAN snapshot
    ocean                JSONB,
    -- ocean structure: {"openness": 0.7, "conscientiousness": 0.6, ...}
    persona_attributes   JSONB,
    -- v2.0 new: raw Exposure/Deliberation text
    free_text_reaction   TEXT,
    exposure_output      JSONB,
    deliberation_output  JSONB,
    -- v2.0 change: signals → distribution format
    signals              JSONB NOT NULL,
    -- signals v2.0 structure:
    -- {
    --   "attention":         {"mean": 0.62, "std": 0.11, "p10": 0.47, "p90": 0.78, "raw_probs": [...]},
    --   "sentiment":         {"mean": 0.18, "std": 0.19, "p10": -0.08, "p90": 0.44, "raw_probs": [...]},
    --   "click_intent":      {"mean": 0.58, "std": 0.14, "raw_probs": [...]},
    --   "conversion_intent": {"mean": 0.31, "std": 0.12, "raw_probs": [...]},
    --   "comprehension":     {"mean": 0.71, "std": 0.09, "raw_probs": [...]},
    --   "recall":            {"mean": 0.55, "std": 0.13, "raw_probs": [...]}
    -- }
    confidence           FLOAT CHECK (confidence >= 0.0 AND confidence <= 1.0),
    is_outlier           BOOLEAN NOT NULL DEFAULT FALSE,
    outlier_reason       TEXT,
    anchor_version       VARCHAR(20) DEFAULT 'v1.0',
    embedding_model      VARCHAR(50) DEFAULT 'text-embedding-3-small',
    response_time_ms     INTEGER,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Debate Agent Results [7.8]
-- ============================================================

CREATE TABLE debate_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    debate_rounds       JSONB,
    moderator_synthesis TEXT,
    score_adjustments   JSONB,
    -- score_adjustments: {persona_id → {before, after, delta}}
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Reports
-- ============================================================

CREATE TABLE reports (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID NOT NULL UNIQUE REFERENCES simulations(id) ON DELETE CASCADE,
    report_data   JSONB NOT NULL,
    -- report_data structure:
    -- {
    --   "p0": {aggregated purchase intent distribution, KOBACO comparison},
    --   "p1": {other signals, KPI, funnel},
    --   "validation": {spearman_r, ks_similarity}
    -- }
    pdf_url       TEXT,
    disclaimer    TEXT NOT NULL DEFAULT
        'Results are AI simulation-based predictions. Actual ad performance may differ by ±20~30%.',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Inquiries (v2.0 new)
-- ============================================================

CREATE TABLE inquiries (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
    title         VARCHAR(300) NOT NULL,
    content       TEXT NOT NULL,
    contact_email VARCHAR(255),
    is_resolved   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Ad Generator (생성모드 — migration 003)
-- ============================================================

CREATE TABLE ad_generations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            UUID REFERENCES projects(id) ON DELETE SET NULL,
    status                VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending | running | completed | failed
    input                 JSONB NOT NULL,
    product_analysis      JSONB,
    strategies            JSONB,
    selected_candidate_id UUID,
    error_message         TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ad_generation_candidates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id UUID NOT NULL REFERENCES ad_generations(id) ON DELETE CASCADE,
    idx           SMALLINT NOT NULL,
    strategy      JSONB,
    template_id   VARCHAR(10),
    copy          JSONB,
    image_prompt  TEXT,
    s3_key        VARCHAR(512),
    qa_result     JSONB,
    qa_passed     BOOLEAN,
    explanation   JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ad_publish_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id    UUID REFERENCES ad_generations(id) ON DELETE SET NULL,
    candidate_id     UUID REFERENCES ad_generation_candidates(id) ON DELETE SET NULL,
    platform         VARCHAR(20) NOT NULL DEFAULT 'instagram',
    status           VARCHAR(20) NOT NULL,  -- published | failed | mocked
    ig_container_id  VARCHAR(100),
    ig_media_id      VARCHAR(100),
    caption          TEXT,
    request_payload  JSONB,
    response_payload JSONB,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Chat Sessions / Messages
-- ============================================================

CREATE TABLE chat_sessions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    project_id  UUID REFERENCES projects(id) ON DELETE SET NULL,
    title       VARCHAR(200) NOT NULL DEFAULT 'New Chat',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role        chat_role NOT NULL,
    content     TEXT NOT NULL,
    metadata    JSONB,
    tokens_used INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Generated Ads [7.8]
-- ============================================================

CREATE TABLE generated_ads (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_by       UUID NOT NULL REFERENCES users(id),
    prompt           TEXT NOT NULL,
    ad_type          VARCHAR(20) NOT NULL,  -- 'text' | 'image' | 'video'
    generation_model VARCHAR(50),           -- 'gemini-flash-3.0' | 'gpt-image-2' | 'gemini-omni'
    status           ad_status NOT NULL DEFAULT 'pending',
    result_url       TEXT,
    storage_path     TEXT,
    is_saved         BOOLEAN NOT NULL DEFAULT FALSE,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- User Settings
-- ============================================================

CREATE TABLE user_settings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    theme         VARCHAR(10) NOT NULL DEFAULT 'light',
    notifications JSONB NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Audit Logs
-- ============================================================

CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
    action      VARCHAR(100) NOT NULL,
    resource    VARCHAR(50),
    resource_id UUID,
    metadata    JSONB,
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX idx_users_org          ON users(organization_id);
CREATE INDEX idx_users_email        ON users(email);
CREATE INDEX idx_projects_org       ON projects(organization_id);
CREATE INDEX idx_ads_project        ON ads(project_id);
CREATE INDEX idx_simulations_ad     ON simulations(ad_id);
CREATE INDEX idx_simulations_status ON simulations(status);
CREATE INDEX idx_persona_resp_sim   ON persona_responses(simulation_id);
CREATE INDEX idx_persona_resp_seg   ON persona_responses(segment);
CREATE INDEX idx_chat_sessions_user ON chat_sessions(user_id);
CREATE INDEX idx_chat_msgs_session  ON chat_messages(session_id, created_at);
CREATE INDEX idx_inquiries_resolved ON inquiries(is_resolved, created_at);
CREATE INDEX idx_ad_generation_candidates_generation ON ad_generation_candidates(generation_id);
CREATE INDEX idx_audit_created      ON audit_logs(created_at DESC);

-- pgvector IVFFlat (for RAG persona search)
CREATE INDEX idx_persona_templates_emb
    ON persona_templates USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ============================================================
-- updated_at triggers
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_organizations_upd BEFORE UPDATE ON organizations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_upd         BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_projects_upd      BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_ads_upd           BEFORE UPDATE ON ads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_chat_sessions_upd BEFORE UPDATE ON chat_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_user_settings_upd BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
```

---

## Alembic Migration Strategy

```
backend/
└── alembic/
    ├── env.py
    ├── alembic.ini
    └── versions/
        ├── 001_initial_schema.py       ← v1.0 table creation
        ├── 002_v2_persona_signals.py   ← persona_responses signals → distribution structure
        └── 003_add_generator_tables.py ← ad_generations / candidates / publish_logs
```

### Key Migration (001→002)

```python
# alembic/versions/002_v2_persona_signals.py

def upgrade():
    op.add_column('persona_responses', sa.Column('ocean', postgresql.JSONB()))
    op.add_column('persona_responses', sa.Column('free_text_reaction', sa.Text()))
    op.add_column('persona_responses', sa.Column('exposure_output', postgresql.JSONB()))
    op.add_column('persona_responses', sa.Column('deliberation_output', postgresql.JSONB()))
    op.add_column('persona_responses',
        sa.Column('anchor_version', sa.String(20), server_default='v1.0'))

    op.create_table('inquiries', ...)

    # survey removal from simulation_type (apply after review)
    # op.execute("ALTER TYPE simulation_type DROP VALUE 'survey'")
    # PostgreSQL does not support dropping enum values → must create new enum and swap


def downgrade():
    op.drop_column('persona_responses', 'ocean')
    op.drop_column('persona_responses', 'free_text_reaction')
    op.drop_column('persona_responses', 'exposure_output')
    op.drop_column('persona_responses', 'deliberation_output')
    op.drop_column('persona_responses', 'anchor_version')
    op.drop_table('inquiries')
```

---

## Table Relationship Summary

```
organizations
    └── users (N)
        └── refresh_tokens (N)
        └── user_settings (1)
    └── projects (N)
        └── project_members (N)  ← users [7.8]
        └── ads (N)
            └── simulations (N)
                └── persona_responses (N)  ← v2.0 extended
                └── debate_results (1)     ← [7.8]
                └── reports (1)
        └── chat_sessions (N)
            └── chat_messages (N)
        └── generated_ads (N)              ← [7.8]
        └── ad_generations (N)             ← 생성모드 (6.12)
            └── ad_generation_candidates (3 per generation)
            └── ad_publish_logs (N)

inquiries (standalone)        ← v2.0 new
persona_templates (standalone) ← for RAG
audit_logs (standalone)
```
