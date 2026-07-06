# ClickMe DB Schema

| Version | v4.0 |
|---|---|
| Date | 2026-06-18 |
| DB | NeonDB (PostgreSQL 18.4 + pgvector) |
| Source | `pg_dump --schema-only` 실측 (public 스키마 전체) |

> v4.0 변경 — 실 DB를 pg_dump로 전량 재추출. 테이블 30 → **45개**, ENUM 타입 10종 명시.
> 신규: `teams`·`project_members`·`refresh_tokens`·`user_settings`·`audit_logs`·`chat_messages`·`generated_ads`·`persona_templates`·`brand_profiles`·`calibration_data`·`ad_campaign_logs`·`kinds`·`categories`·`category_kinds`·`alembic_version`.
> 변경: `users` `email`→`login_id`, `team_id`·`phone_num`·`user_email`·`must_change_password` 추가 / 여러 테이블에 `deleted_at` 소프트삭제 컬럼 추가.
>
> **admin 소프트삭제** — 조직/유저 삭제는 hard delete가 아니라 `status='INACTIVE'`(+ Cognito disable)로 처리해 데이터는 보존한다. 복원 시 `status='ACTIVE'`, 영구삭제(purge) 시에만 행을 실제로 지운다. auth 미들웨어가 `status != 'ACTIVE'`면 401 차단.
>
> **Alembic 체인(현행)** — `0001_baseline`(구 001~029 squash) → `0002_persona_weight` → `0003_categories_kinds` → `0004_generator_kb_search_vector`. 구 3자리 리비전(001/002…)은 제거됨. 새 DB는 `0001_baseline`이 전체 스키마를 한 번에 생성.

---

## 테이블 목록 (46개)

### 인증 · 사용자
| 테이블 | 역할 |
|---|---|
| `users` | 사용자 (로그인 ID = `login_id`) |
| `teams` | 팀 (조직 하위 협업 단위) |
| `refresh_tokens` | JWT 리프레시 토큰 |
| `user_settings` | 사용자별 설정(테마·알림) |
| `audit_logs` | 사용자 행위 감사 로그 |

### 조직 · 빌링
| 테이블 | 역할 |
|---|---|
| `organizations` | 기업(빌링 단위) |
| `organization_members` | 기업-사용자 매핑 |
| `organization_subscriptions` | 기업 구독 |
| `subscription_plans` | 구독 플랜 정의 |
| `project_members` | 프로젝트 협업 멤버(뷰어/에디터/오너) |

### 프로젝트 · 광고
| 테이블 | 역할 |
|---|---|
| `projects` | 프로젝트(캠페인 단위) |
| `ads` | 광고 소재 |
| `ad_analyses` | 광고 분석 결과 |
| `ad_embeddings` | 광고 벡터 임베딩 |
| `rubric_scores` | 광고 루브릭 점수 |

### 시뮬레이션 (4-1)
| 테이블 | 역할 |
|---|---|
| `panels` | 페르소나 패널 |
| `personas` | 개별 페르소나 |
| `persona_templates` | 페르소나 템플릿(클러스터·임베딩) |
| `simulations` | 시뮬레이션 실행 단위 |
| `persona_responses` | 페르소나별 반응 |
| `simulation_aggregates` | 시뮬레이션 집계 결과 |
| `simulation_results` | 시뮬레이션 결과(분포/페르소나, 임시) |
| `simulation_comparisons` | A/B 비교 |
| `diagnoses` | 시뮬레이션 진단 |
| `recommendations` | 개선 추천 |
| `reports` | PDF 리포트 |

### 페르소나 토론
| 테이블 | 역할 |
|---|---|
| `persona_debates` | 페르소나 토론 세션 (simulations 1:N) |
| `persona_debate_participants` | 토론 패널 |
| `persona_debate_utterances` | 토론 발언 로그(라운드×패널) |

### 광고 생성 (4-3) · 게시
| 테이블 | 역할 |
|---|---|
| `ad_generations` | 광고 제너레이터 실행 |
| `ad_generation_candidates` | 제너레이터 후보 |
| `ad_publish_logs` | 광고 게시 이력(IG) |
| `ad_campaign_logs` | Meta Marketing API 집행 이력 |
| `generated_ads` | 생성 이미지 광고(독립 저장) |
| `brand_profiles` | 클라이언트 브랜드 프로필 |

### 매니지먼트 (4-2)
| 테이블 | 역할 |
|---|---|
| `management_notifications` | 이상 감지 운영 알림(하이브리드 C안) — 채팅과 분리 저장, org·kind·dedup_key 미해결 1행 |

### 참조 · 기타
| 테이블 | 역할 |
|---|---|
| `benchmarks` | 업종별 벤치마크 |
| `rag_chunks` | RAG 청크 |
| `calibration_data` | 예측↔실측 캘리브레이션 데이터 |
| `kinds` | NICE 상품/서비스 분류 45류 |
| `categories` | 업종 카테고리 묶음 |
| `category_kinds` | 카테고리↔류 매핑(다대다) |
| `chat_sessions` | 채팅 세션 |
| `chat_messages` | 채팅 메시지 |
| `inquiries` | 고객 문의 |
| `alembic_version` | Alembic 마이그레이션 버전 |

---

## ENUM 타입 (10종)

> DB에 타입은 정의돼 있으나, 대부분의 테이블은 `VARCHAR + 앱 레벨 검증`을 사용한다.
> 실제 ENUM 컬럼은 `generated_ads.status`(ad_status) · `chat_messages.role`(chat_role) · `project_members.role`(project_member_role) 셋뿐.

| 타입 | 값 | 사용처 |
|---|---|---|
| `ad_input_type` | image, text, video, url | (미사용 — `ads.media_type`는 VARCHAR) |
| `ad_status` | pending, analyzing, completed, failed | `generated_ads.status` |
| `campaign_objective` | awareness, conversion, lead_gen, app_install, retention, product_launch, promotion | (미사용) |
| `chat_role` | user, assistant | `chat_messages.role` |
| `plan_type` | free, professional, enterprise | (미사용 — VARCHAR 사용) |
| `project_member_role` | owner, editor, viewer | `project_members.role` |
| `project_status` | active, archived | (미사용) |
| `simulation_status` | pending, running, completed, failed | (미사용) |
| `simulation_type` | ad_reaction, survey | (미사용) |
| `user_role` | admin, user | (미사용 — `users.role`는 VARCHAR) |

확장: `uuid-ossp`, `vector`(pgvector, ivfflat/hnsw).

---

## Full Schema (실측)

```sql
-- ============================================================
-- users  (⚠️ 로그인 식별자 = login_id, email 아님)
-- ============================================================
CREATE TABLE users (
    id                   UUID PRIMARY KEY,
    login_id             VARCHAR(255) NOT NULL UNIQUE,    -- 로그인 ID
    password_hash        VARCHAR(255) NOT NULL,
    name                 VARCHAR(100) NOT NULL,
    role                 VARCHAR(20)  NOT NULL,                    -- ADMIN | COMPANY | USER
    status               VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE | PENDING | INACTIVE(admin 소프트삭제)
    must_change_password BOOLEAN      NOT NULL DEFAULT false,      -- 발급 계정 최초 로그인 시 변경 유도
    team_id              UUID REFERENCES teams(id) ON DELETE SET NULL,  -- 소속 팀(USER, 미배정 NULL)
    phone_num            VARCHAR(30),
    user_email           VARCHAR(255),                    -- 연락용(로그인 아님)
    created_by           UUID REFERENCES users(id),
    last_login_at        TIMESTAMP,
    created_at           TIMESTAMP NOT NULL DEFAULT now(),
    updated_at           TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_team ON users(team_id);

-- ============================================================
-- teams
-- ============================================================
CREATE TABLE teams (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID         NOT NULL REFERENCES organizations(id),
    name            VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP    NOT NULL DEFAULT now()
);
CREATE INDEX idx_teams_org ON teams(organization_id);

-- ============================================================
-- refresh_tokens
-- ============================================================
CREATE TABLE refresh_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID         NOT NULL,            -- ⚠️ FK 미선언(컬럼만)
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ  NOT NULL,
    revoked    BOOLEAN      NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ============================================================
-- user_settings
-- ============================================================
CREATE TABLE user_settings (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID        NOT NULL UNIQUE,   -- ⚠️ FK 미선언
    theme         VARCHAR(10) NOT NULL,
    notifications JSONB       NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- audit_logs  (FK 미선언 — user_id/resource_id는 느슨 참조)
-- ============================================================
CREATE TABLE audit_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID,
    action      VARCHAR(100) NOT NULL,
    resource    VARCHAR(50),
    resource_id UUID,
    metadata    JSONB,
    ip_address  VARCHAR(45),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- organizations
-- ============================================================
CREATE TABLE organizations (
    id         UUID PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    slug       VARCHAR(100) NOT NULL UNIQUE,
    status     VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | INACTIVE(admin 소프트삭제)
    plan       VARCHAR(50)  DEFAULT 'free',             -- free | professional | enterprise
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================
-- organization_members
-- ============================================================
CREATE TABLE organization_members (
    id              UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    user_id         UUID NOT NULL REFERENCES users(id),
    role            VARCHAR(20) NOT NULL,              -- OWNER | MANAGER | MEMBER
    invited_by      UUID REFERENCES users(id),
    status          VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- ACTIVE | PENDING | REJECTED
    joined_at       TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    CONSTRAINT uq_org_member UNIQUE (organization_id, user_id)
);

-- ============================================================
-- subscription_plans
-- ============================================================
CREATE TABLE subscription_plans (
    id               UUID PRIMARY KEY,
    plan_type        VARCHAR(20)  NOT NULL UNIQUE,
    name             VARCHAR(100) NOT NULL,
    simulation_limit INTEGER      NOT NULL,
    price_monthly    NUMERIC      NOT NULL DEFAULT 0,
    price_yearly     NUMERIC      NOT NULL DEFAULT 0,
    features         JSONB        NOT NULL,
    is_active        BOOLEAN      NOT NULL DEFAULT true,
    created_at       TIMESTAMP    NOT NULL DEFAULT now()
);

-- ============================================================
-- organization_subscriptions
-- ============================================================
CREATE TABLE organization_subscriptions (
    id              UUID PRIMARY KEY,
    organization_id UUID NOT NULL REFERENCES organizations(id),
    plan_id         UUID NOT NULL REFERENCES subscription_plans(id),
    status          VARCHAR(20)  NOT NULL,
    started_at      TIMESTAMP    NOT NULL,
    expires_at      TIMESTAMP,
    created_at      TIMESTAMP    NOT NULL DEFAULT now()
);

-- ============================================================
-- project_members  (FK 미선언 — project_id/user_id는 느슨 참조)
-- ============================================================
CREATE TABLE project_members (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    user_id    UUID NOT NULL,
    role       project_member_role NOT NULL,      -- owner | editor | viewer (ENUM)
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_project_members UNIQUE (project_id, user_id)
);

-- ============================================================
-- projects  (소프트삭제: deleted_at)
-- ============================================================
CREATE TABLE projects (
    id              UUID PRIMARY KEY,
    organization_id UUID         NOT NULL REFERENCES organizations(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    status          VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | DELETED
    created_by      UUID         NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMP
);
CREATE INDEX idx_projects_deleted_at ON projects(deleted_at);

-- ============================================================
-- ads
-- ============================================================
CREATE TABLE ads (
    id                UUID PRIMARY KEY,
    project_id        UUID         NOT NULL REFERENCES projects(id),
    title             VARCHAR(255) NOT NULL,
    media_type        VARCHAR(20)  NOT NULL,           -- image | text | video | url
    asset_url         VARCHAR(500),
    copy_text         TEXT,
    industry_category VARCHAR(100),
    product_category  VARCHAR(100),
    ad_objective      VARCHAR(50),
    target_filter     JSONB,
    status            VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',  -- DRAFT | ACTIVE | ARCHIVED
    created_by        UUID REFERENCES users(id),
    created_at        TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP    NOT NULL DEFAULT now()
);

-- ============================================================
-- ad_analyses
-- ============================================================
CREATE TABLE ad_analyses (
    id                  UUID PRIMARY KEY,
    ad_id               UUID         NOT NULL REFERENCES ads(id),
    structured_analysis JSONB        NOT NULL,
    detected_industry   VARCHAR(100),
    detected_target     VARCHAR(100),
    detected_message    TEXT,
    intent_mismatch     BOOLEAN      NOT NULL DEFAULT false,
    mismatch_detail     JSONB,
    model_version       VARCHAR(50)  NOT NULL,
    created_at          TIMESTAMP    NOT NULL DEFAULT now(),
    detected_objective  VARCHAR(50)
);

-- ============================================================
-- ad_embeddings
-- ============================================================
CREATE TABLE ad_embeddings (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ad_id      UUID NOT NULL REFERENCES ads(id),
    content    TEXT,
    embedding  vector(1536),
    created_at TIMESTAMP DEFAULT now()
);

-- ============================================================
-- rubric_scores
-- ============================================================
CREATE TABLE rubric_scores (
    id              UUID PRIMARY KEY,
    ad_analysis_id  UUID        NOT NULL REFERENCES ad_analyses(id),
    dimension       VARCHAR(50) NOT NULL,
    score           INTEGER     NOT NULL,
    evidence        JSONB       NOT NULL,
    created_at      TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT uq_rubric UNIQUE (ad_analysis_id, dimension)
);

-- ============================================================
-- panels
-- ============================================================
CREATE TABLE panels (
    id             UUID PRIMARY KEY,
    version        VARCHAR(20)  NOT NULL UNIQUE,
    size           INTEGER      NOT NULL,
    seed           VARCHAR(50)  NOT NULL,
    model_version  VARCHAR(50)  NOT NULL,
    grounding_meta JSONB        NOT NULL,
    status         VARCHAR(20)  NOT NULL DEFAULT 'BUILDING',  -- BUILDING | READY | DEPRECATED
    built_at       TIMESTAMP,
    created_at     TIMESTAMP    NOT NULL DEFAULT now()
);

-- ============================================================
-- personas
-- ============================================================
CREATE TABLE personas (
    id                 UUID PRIMARY KEY,
    panel_id           UUID        NOT NULL REFERENCES panels(id),
    age                INTEGER     NOT NULL,
    gender             VARCHAR(10) NOT NULL,
    region             VARCHAR(50) NOT NULL,
    ocean              JSONB       NOT NULL,
    media_behavior     JSONB       NOT NULL,
    consumption_values JSONB       NOT NULL,
    profile_narrative  TEXT        NOT NULL,
    created_at         TIMESTAMP   NOT NULL DEFAULT now(),
    socioeconomic      JSONB       NOT NULL DEFAULT '{}'::jsonb
);

-- ============================================================
-- persona_templates  (FK 미선언)
-- ============================================================
CREATE TABLE persona_templates (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(100),
    cluster_id VARCHAR(50),
    attributes JSONB        NOT NULL,
    embedding  vector(1536),
    is_public  BOOLEAN      NOT NULL,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- ============================================================
-- simulations  (소프트삭제: deleted_at)
-- ============================================================
CREATE TABLE simulations (
    id                 UUID PRIMARY KEY,
    ad_id              UUID        NOT NULL REFERENCES ads(id),
    ad_analysis_id     UUID        NOT NULL REFERENCES ad_analyses(id),
    panel_id           UUID        REFERENCES panels(id),         -- nullable
    organization_id    UUID        NOT NULL REFERENCES organizations(id),
    target_filter      JSONB,
    target_mode        VARCHAR(10) NOT NULL DEFAULT 'AUTO',
    sample_size        INTEGER     NOT NULL,
    qa_passed_count    INTEGER,
    low_sample_warning BOOLEAN     NOT NULL DEFAULT false,
    status             VARCHAR(20) NOT NULL DEFAULT 'QUEUED',  -- QUEUED | RUNNING | COMPLETED | FAILED
    model_version      VARCHAR(50) NOT NULL DEFAULT 'gpt-4o-mini',
    error_detail       JSONB,
    created_by         UUID        REFERENCES users(id),         -- nullable
    started_at         TIMESTAMP,
    completed_at       TIMESTAMP,
    created_at         TIMESTAMP   NOT NULL DEFAULT now(),
    deleted_at         TIMESTAMP
);
CREATE INDEX idx_simulations_deleted_at ON simulations(deleted_at);

-- ============================================================
-- persona_responses
-- ============================================================
CREATE TABLE persona_responses (
    id                   UUID PRIMARY KEY,
    simulation_id        UUID          NOT NULL REFERENCES simulations(id),
    persona_id           UUID          NOT NULL REFERENCES personas(id),
    exposure_context     VARCHAR(50),
    aisas                JSONB         NOT NULL,
    drop_stage           VARCHAR(20),
    drop_reason_tag      VARCHAR(50),
    purchase_intent      INTEGER       NOT NULL,
    trust                INTEGER       NOT NULL,
    rejected             BOOLEAN       NOT NULL DEFAULT false,
    rejection_reason_tag VARCHAR(50),
    emotion_tag          VARCHAR(50)   NOT NULL,
    perceived_message    TEXT,
    perceived_target     VARCHAR(100),
    utterance            TEXT,
    qa_passed            BOOLEAN       NOT NULL,
    qa_fail_reason       VARCHAR(100),
    created_at           TIMESTAMP     NOT NULL DEFAULT now(),
    weight               NUMERIC(10,4) NOT NULL DEFAULT 1.0,
    CONSTRAINT uq_response UNIQUE (simulation_id, persona_id)
);

-- ============================================================
-- simulation_aggregates
-- ============================================================
CREATE TABLE simulation_aggregates (
    id                  UUID PRIMARY KEY,
    simulation_id       UUID          NOT NULL UNIQUE REFERENCES simulations(id),
    click_intent_rate   NUMERIC       NOT NULL,
    ci_low              NUMERIC       NOT NULL,
    ci_high             NUMERIC       NOT NULL,
    purchase_intent_avg NUMERIC       NOT NULL,
    trust_avg           NUMERIC       NOT NULL,
    rejection_rate      NUMERIC       NOT NULL,
    variance_warning    BOOLEAN       NOT NULL DEFAULT false,
    payload             JSONB         NOT NULL,
    engine_version      VARCHAR(50)   NOT NULL,
    created_at          TIMESTAMP     NOT NULL DEFAULT now(),
    effective_n         NUMERIC(10,1) NOT NULL DEFAULT 0.0
);

-- ============================================================
-- simulation_results  (현재 파이프라인 임시 저장용)
-- ============================================================
CREATE TABLE simulation_results (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ad_id         UUID    NOT NULL REFERENCES ads(id),
    persona_count INTEGER,
    distribution  JSONB,
    personas      JSONB,
    created_at    TIMESTAMP DEFAULT now()
);

-- ============================================================
-- simulation_comparisons
-- ============================================================
CREATE TABLE simulation_comparisons (
    id              UUID PRIMARY KEY,
    project_id      UUID NOT NULL REFERENCES projects(id),
    simulation_a_id UUID NOT NULL REFERENCES simulations(id),
    simulation_b_id UUID NOT NULL REFERENCES simulations(id),
    result          JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- ============================================================
-- diagnoses
-- ============================================================
CREATE TABLE diagnoses (
    id              UUID PRIMARY KEY,
    simulation_id   UUID        NOT NULL REFERENCES simulations(id),
    dimension       VARCHAR(50) NOT NULL,
    rubric_score    INTEGER     NOT NULL,
    benchmark_key   VARCHAR(100),
    diagnosis_text  TEXT        NOT NULL,
    consensus_type  VARCHAR(20) NOT NULL,
    dissent_block   JSONB,
    evidence_refs   JSONB       NOT NULL,
    created_at      TIMESTAMP   NOT NULL DEFAULT now(),
    CONSTRAINT uq_diagnosis UNIQUE (simulation_id, dimension)
);

-- ============================================================
-- recommendations
-- ============================================================
CREATE TABLE recommendations (
    id                    UUID PRIMARY KEY,
    simulation_id         UUID        NOT NULL REFERENCES simulations(id),
    diagnosis_id          UUID        NOT NULL REFERENCES diagnoses(id),
    dimension             VARCHAR(50) NOT NULL,
    grade                 VARCHAR(20) NOT NULL,
    priority              INTEGER     NOT NULL,
    recommendation_text   TEXT        NOT NULL,
    diagnosis_evidence    JSONB       NOT NULL,
    prescription_evidence JSONB,
    created_at            TIMESTAMP   NOT NULL DEFAULT now()
);

-- ============================================================
-- reports
-- ============================================================
CREATE TABLE reports (
    id               UUID PRIMARY KEY,
    simulation_id    UUID        NOT NULL REFERENCES simulations(id),
    template_version VARCHAR(20) NOT NULL,
    panel_version    VARCHAR(20) NOT NULL,
    model_version    VARCHAR(50) NOT NULL,
    payload          JSONB       NOT NULL,
    file_url         VARCHAR(500),
    created_at       TIMESTAMP   NOT NULL DEFAULT now()
);

-- ============================================================
-- persona_debates  (페르소나 토론 세션, simulations 1:N)
-- ============================================================
CREATE TABLE persona_debates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id UUID        NOT NULL REFERENCES simulations(id) ON DELETE CASCADE,
    topic         TEXT,
    rounds_run    INTEGER,                            -- 실제 돈 라운드(2~4)
    stop_reason   VARCHAR(20),                        -- consensus | dissensus | max
    judge_model   VARCHAR(50),
    engines       JSONB,                              -- ["haiku","gpt","gemini"]
    judge_log     JSONB,
    final         JSONB,                              -- headline/consensus/dissent/ranked_actions
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING | RUNNING | COMPLETED | FAILED
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_persona_debates_sim ON persona_debates(simulation_id);

-- ============================================================
-- persona_debate_participants  (debate 1:N)
-- ============================================================
CREATE TABLE persona_debate_participants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debate_id       UUID        NOT NULL REFERENCES persona_debates(id) ON DELETE CASCADE,
    persona_id      VARCHAR(50) NOT NULL,            -- "P-00011"(더미 문자열·실 UUID 양쪽)
    persona_name    VARCHAR(50),
    persona_profile TEXT,
    role            VARCHAR(20),                     -- 피벗/완주자/거부자/불신자/초기이탈/미온2
    engine          VARCHAR(20),                     -- haiku/gpt/gemini
    CONSTRAINT persona_debate_participants_debate_id_persona_id_key UNIQUE (debate_id, persona_id)
);

-- ============================================================
-- persona_debate_utterances  (LLM 발언 로그, 라운드×패널)
-- ============================================================
CREATE TABLE persona_debate_utterances (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    debate_id      UUID    NOT NULL REFERENCES persona_debates(id) ON DELETE CASCADE,
    participant_id UUID    REFERENCES persona_debate_participants(id) ON DELETE CASCADE,
    round          INTEGER NOT NULL,                 -- 1~4
    phase          VARCHAR(10),                      -- 발산/반박/검증
    stance         VARCHAR(10),                      -- positive/neutral/negative
    text           TEXT,
    reason         TEXT,
    lever          TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_persona_debate_utt_debate ON persona_debate_utterances(debate_id);

-- ============================================================
-- ad_generations  (소프트삭제: deleted_at)
-- ============================================================
CREATE TABLE ad_generations (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            UUID REFERENCES projects(id) ON DELETE SET NULL,
    status                VARCHAR(20) DEFAULT 'pending',  -- pending | running | completed | failed
    input                 JSONB,
    product_analysis      JSONB,
    strategies            JSONB,
    selected_candidate_id UUID,
    error_message         TEXT,
    created_at            TIMESTAMP DEFAULT now(),
    updated_at            TIMESTAMP DEFAULT now(),
    created_by            UUID REFERENCES users(id),
    deleted_at            TIMESTAMP
);
CREATE INDEX idx_ad_generations_deleted_at ON ad_generations(deleted_at);

-- ============================================================
-- ad_generation_candidates
-- ============================================================
CREATE TABLE ad_generation_candidates (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id UUID        NOT NULL REFERENCES ad_generations(id) ON DELETE CASCADE,
    idx           SMALLINT,
    strategy      JSONB,
    template_id   VARCHAR(10),
    copy          JSONB,
    image_prompt  TEXT,
    s3_key        VARCHAR(512),
    qa_result     JSONB,
    qa_passed     BOOLEAN,
    explanation   JSONB,
    created_at    TIMESTAMP DEFAULT now()
);
CREATE INDEX idx_ad_generation_candidates_generation ON ad_generation_candidates(generation_id);

-- ============================================================
-- ad_publish_logs
-- ============================================================
CREATE TABLE ad_publish_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id    UUID REFERENCES ad_generations(id) ON DELETE SET NULL,
    candidate_id     UUID REFERENCES ad_generation_candidates(id) ON DELETE SET NULL,
    platform         VARCHAR(20) DEFAULT 'instagram',
    status           VARCHAR(20),
    ig_container_id  VARCHAR(100),
    ig_media_id      VARCHAR(100),
    caption          TEXT,
    request_payload  JSONB,
    response_payload JSONB,
    error_message    TEXT,
    created_at       TIMESTAMP DEFAULT now()
);

-- ============================================================
-- ad_campaign_logs  (Meta Marketing API 집행 이력)
-- ============================================================
CREATE TABLE ad_campaign_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generation_id    UUID REFERENCES ad_generations(id) ON DELETE SET NULL,
    candidate_id     UUID REFERENCES ad_generation_candidates(id) ON DELETE SET NULL,
    status           VARCHAR(20) NOT NULL,            -- created | failed | mocked
    mocked           BOOLEAN     NOT NULL DEFAULT false,
    campaign_id      VARCHAR(100),
    adset_id         VARCHAR(100),
    creative_id      VARCHAR(100),
    ad_id            VARCHAR(100),                     -- 플랫폼 광고 ID(문자열)
    budget           INTEGER,
    objective        VARCHAR(50),
    targeting        JSONB,
    request_payload  JSONB,
    response_payload JSONB,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ad_campaign_logs_generation ON ad_campaign_logs(generation_id);

-- ============================================================
-- generated_ads  (이미지 생성 광고, FK 미선언)
-- ============================================================
CREATE TABLE generated_ads (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       UUID        NOT NULL,
    created_by       UUID        NOT NULL,
    prompt           TEXT        NOT NULL,
    style            VARCHAR(50),
    aspect_ratio     VARCHAR(10) NOT NULL,
    status           ad_status   NOT NULL,            -- pending | analyzing | completed | failed (ENUM)
    image_url        TEXT,
    storage_path     TEXT,
    is_saved         BOOLEAN     NOT NULL,
    saved_at         TIMESTAMPTZ,
    generation_model VARCHAR(50),
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- brand_profiles
-- ============================================================
CREATE TABLE brand_profiles (
    client_id        VARCHAR(64) PRIMARY KEY,
    brand_color      VARCHAR(20),
    brand_logo_key   VARCHAR(512),
    tone_and_manner  TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- benchmarks
-- ============================================================
CREATE TABLE benchmarks (
    id          UUID PRIMARY KEY,
    industry    VARCHAR(100) NOT NULL,
    metric      VARCHAR(50)  NOT NULL,
    value_low   NUMERIC      NOT NULL,
    value_high  NUMERIC      NOT NULL,
    unit        VARCHAR(20)  NOT NULL,
    source_name VARCHAR(255) NOT NULL,
    source_year INTEGER      NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT now(),
    CONSTRAINT uq_bench UNIQUE (industry, metric)
);

-- ============================================================
-- rag_chunks
-- ============================================================
CREATE TABLE rag_chunks (
    chunk_id    VARCHAR(100) PRIMARY KEY,
    tier        VARCHAR(10)  NOT NULL,
    dimension   VARCHAR(50)  NOT NULL,
    media_type  VARCHAR(20)  NOT NULL,
    industry    VARCHAR(100),
    source_name VARCHAR(255) NOT NULL,
    content     TEXT         NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT now()
);

-- ============================================================
-- calibration_data  (예측 CTR ↔ 실측 CTR, FK 미선언)
-- ============================================================
CREATE TABLE calibration_data (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    simulation_id       UUID,
    predicted_ctr_score DOUBLE PRECISION,
    actual_ctr_percent  DOUBLE PRECISION,
    industry            VARCHAR(50),
    platform            VARCHAR(50),
    ad_format           VARCHAR(30),
    submitted_by        UUID,
    verified            BOOLEAN     NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- kinds  (NICE 상품/서비스 분류 45류)
-- ============================================================
CREATE TABLE kinds (
    id          SMALLINT PRIMARY KEY,    -- 류 번호 1~45
    description TEXT NOT NULL
);

-- ============================================================
-- categories  (업종 카테고리 묶음)
-- ============================================================
CREATE TABLE categories (
    id   SMALLINT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

-- ============================================================
-- category_kinds  (카테고리 ↔ 류 다대다 매핑)
-- ============================================================
CREATE TABLE category_kinds (
    category_id SMALLINT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    kind_id     SMALLINT NOT NULL REFERENCES kinds(id)      ON DELETE CASCADE,
    PRIMARY KEY (category_id, kind_id)
);
CREATE INDEX idx_category_kinds_kind ON category_kinds(kind_id);

-- ============================================================
-- chat_sessions
-- ============================================================
CREATE TABLE chat_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    messages   JSONB     DEFAULT '[]',
    created_at TIMESTAMP DEFAULT now()
);

-- ============================================================
-- chat_messages  (FK 미선언 — session_id는 느슨 참조)
-- ============================================================
CREATE TABLE chat_messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id  UUID        NOT NULL,
    role        chat_role   NOT NULL,                -- user | assistant (ENUM)
    content     TEXT        NOT NULL,
    metadata    JSONB,
    tokens_used INTEGER,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================
-- inquiries
-- ============================================================
CREATE TABLE inquiries (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name       VARCHAR(255),
    email      VARCHAR(255),
    message    TEXT,
    created_at TIMESTAMP DEFAULT now()
);

-- ============================================================
-- management_notifications  (운영 알림, 이상 감지 C안 — 0005)
-- ============================================================
CREATE TABLE management_notifications (
    id                  UUID PRIMARY KEY,
    organization_id     UUID         NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    project_id          UUID         NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    campaign_id         VARCHAR(100),                   -- remediation만 필수
    kind                VARCHAR(60)  NOT NULL,           -- "management.remediation_consult" 등
    dedup_key           VARCHAR(200) NOT NULL,           -- f"{campaign_id}:{anomaly}"
    payload             JSONB        NOT NULL DEFAULT '{}'::jsonb,
    read_at             TIMESTAMPTZ,
    resolved_at         TIMESTAMPTZ,
    resolution          VARCHAR(20),                     -- ignored | actioned | auto_normal
    consult_session_id  UUID,
    last_notified_at    TIMESTAMPTZ  NOT NULL,
    followup_count      INTEGER      NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT now()
);
-- 미해결 알림은 (org, kind, dedup_key)당 1행 (부분 유니크 — 멀티워커 dedup 백스톱)
CREATE UNIQUE INDEX uq_mgmt_notif_open_dedup ON management_notifications (organization_id, kind, dedup_key)
    WHERE resolved_at IS NULL;
CREATE INDEX ix_mgmt_notif_org_recent ON management_notifications (organization_id, last_notified_at DESC);

-- ============================================================
-- alembic_version  (마이그레이션 버전 추적)
-- ============================================================
CREATE TABLE alembic_version (
    version_num VARCHAR(32) PRIMARY KEY
);
```

---

## ORM 모델(`core/models.py`) vs 실제 DB

> `core/models.py`는 전체 테이블의 일부만 선언한다. 시뮬레이션 핵심 테이블(`simulations`·`personas`·`panels`·`ad_analyses`·`persona_responses`·`simulation_aggregates`·`diagnoses`·`recommendations`·`reports` 등)은 도메인 모델/Alembic로만 관리되고 `core/models.py`엔 없다.

| 구분 | 내용 |
|---|---|
| **ORM에 선언, DB에 없음** | `action_proposals`·`approvals`·`audit_events`·`execution_runs`·`idempotency_keys` (management 모델 — 현재 public 스키마 덤프에 부재, **미생성 추정**) |
| **DB에 있음, ORM(core) 없음** | `simulations`·`ad_analyses`·`panels`·`personas`·`persona_templates`·`persona_responses`·`simulation_aggregates`·`simulation_comparisons`·`diagnoses`·`recommendations`·`reports`·`benchmarks`·`rag_chunks`·`rubric_scores`·`subscription_plans`·`organization_subscriptions`·`calibration_data`·`brand_profiles`·`alembic_version` |
| `ads` | ORM `ad_type`/`s3_key`/`analysis` → 실제 `media_type`/`asset_url` + `copy_text`·`industry_category`·`product_category`·`ad_objective`·`target_filter`·`status`·`created_by`·`updated_at` (불일치 지속) |
| `projects` | ORM은 `organization_id`·`name`·`created_at`만 → 실제 `+ description`·`status`·`created_by`·`updated_at`·`deleted_at` |
| `inquiries` | ORM `email` 컬럼 → 실제 `email` (일치) |
| `users` | ORM·DB 모두 `login_id` 기준으로 정렬됨 (v3.1 `email` 표기 해소) |

---

## 관계도 (핵심)

```
organizations
├── teams ──────────────── users(team_id)
├── organization_members → users
├── organization_subscriptions → subscription_plans
└── projects
    ├── project_members (FK 미선언, 느슨 참조)
    ├── ads
    │   ├── ad_analyses
    │   │   └── rubric_scores
    │   ├── ad_embeddings
    │   ├── simulation_results (ad_id 직접 참조)
    │   └── simulations (organization_id도 직접 참조)
    │       ├── persona_responses → personas → panels
    │       ├── simulation_aggregates
    │       ├── persona_debates → persona_debate_participants · persona_debate_utterances
    │       ├── diagnoses → recommendations
    │       ├── reports
    │       └── simulation_comparisons
    ├── ad_generations
    │   ├── ad_generation_candidates
    │   ├── ad_publish_logs
    │   └── ad_campaign_logs
    └── chat_sessions

categories ── category_kinds ── kinds        (업종↔NICE류 매핑, 독립)
독립 테이블: users·refresh_tokens·user_settings·audit_logs·generated_ads·
            brand_profiles·persona_templates·calibration_data·benchmarks·
            rag_chunks·chat_messages·inquiries·alembic_version
```

---

## 참고 문서

| 항목 | 위치 |
|---|---|
| API 엔드포인트 | `docs/api-spec.md` |
| ORM 모델 | `backend/core/models.py` |
| 시뮬레이션 서비스 | `backend/domain/simulation/service/simulation_service.py` |
| 제너레이터 서비스 | `backend/domain/generator/service/generator_service.py` |
