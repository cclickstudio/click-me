# ClickMe DB Schema

| Version | v3.0 (실측 기준) |
|---|---|
| Date | 2026-06-13 |
| DB | NeonDB (PostgreSQL + pgvector) |
| Source | information_schema 직접 조회 결과 |

---

## 테이블 목록 (29개)

| 테이블 | 역할 |
|---|---|
| `users` | 사용자 |
| `organizations` | 기업(빌링 단위) |
| `organization_members` | 기업-사용자 매핑 |
| `organization_subscriptions` | 기업 구독 |
| `subscription_plans` | 구독 플랜 정의 |
| `projects` | 프로젝트 |
| `ads` | 광고 소재 |
| `ad_analyses` | 광고 분석 결과 |
| `ad_embeddings` | 광고 벡터 임베딩 |
| `panels` | 페르소나 패널 |
| `personas` | 개별 페르소나 |
| `simulations` | 시뮬레이션 실행 단위 |
| `persona_responses` | 페르소나별 반응 |
| `simulation_aggregates` | 시뮬레이션 집계 결과 |
| `simulation_results` | 시뮬레이션 결과 (분포/페르소나) |
| `simulation_comparisons` | A/B 비교 |
| `debate_sessions` | 디베이트 세션 [7.8] |
| `debate_statements` | 디베이트 발언 [7.8] |
| `diagnoses` | 시뮬레이션 진단 |
| `rubric_scores` | 광고 루브릭 점수 |
| `recommendations` | 개선 추천 |
| `reports` | PDF 리포트 |
| `benchmarks` | 업종별 벤치마크 |
| `rag_chunks` | RAG 청크 |
| `ad_generations` | 광고 제너레이터 실행 |
| `ad_generation_candidates` | 제너레이터 후보 |
| `ad_publish_logs` | 광고 게시 이력 |
| `chat_sessions` | 채팅 세션 |
| `inquiries` | 고객 문의 |

---

## Full Schema (실측)

```sql
-- ============================================================
-- users
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    name            VARCHAR(100) NOT NULL,
    role            VARCHAR(20)  NOT NULL,            -- ADMIN | COMPANY | USER
    status          VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | PENDING | REJECTED
    created_by      UUID REFERENCES users(id),
    last_login_at   TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);
-- ⚠️ organization_id 컬럼 없음. 소속은 organization_members 경유.

-- ============================================================
-- organizations
-- ============================================================
CREATE TABLE organizations (
    id         UUID PRIMARY KEY,
    name       VARCHAR(255) NOT NULL,
    slug       VARCHAR(100) NOT NULL UNIQUE,
    status     VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | PENDING
    plan       VARCHAR(50)  DEFAULT 'free',             -- free | professional | enterprise
    created_at TIMESTAMP NOT NULL DEFAULT now(),
    updated_at TIMESTAMP NOT NULL DEFAULT now()
);
-- ⚠️ plan_type 컬럼 없음. plan(VARCHAR) 사용.

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
    UNIQUE (organization_id, user_id)
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
-- projects
-- ============================================================
CREATE TABLE projects (
    id              UUID PRIMARY KEY,
    organization_id UUID         NOT NULL REFERENCES organizations(id),
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    status          VARCHAR(20)  NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | DELETED
    created_by      UUID         NOT NULL REFERENCES users(id),
    created_at      TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP    NOT NULL DEFAULT now()
);

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
    industry_category VARCHAR(100) NOT NULL,
    product_category  VARCHAR(100) NOT NULL,
    ad_objective      VARCHAR(50)  NOT NULL,
    target_filter     JSONB,
    status            VARCHAR(20)  NOT NULL DEFAULT 'DRAFT',  -- DRAFT | ACTIVE | ARCHIVED
    created_by        UUID         NOT NULL REFERENCES users(id),
    created_at        TIMESTAMP    NOT NULL DEFAULT now(),
    updated_at        TIMESTAMP    NOT NULL DEFAULT now()
);
-- ⚠️ ORM 모델의 ad_type → 실제 media_type / s3_key → asset_url / analysis 컬럼 없음(ad_analyses 테이블 분리)

-- ============================================================
-- ad_analyses
-- ============================================================
CREATE TABLE ad_analyses (
    id                UUID PRIMARY KEY,
    ad_id             UUID         NOT NULL REFERENCES ads(id),
    structured_analysis JSONB      NOT NULL,
    detected_industry VARCHAR(100),
    detected_target   VARCHAR(100),
    detected_message  TEXT,
    intent_mismatch   BOOLEAN      NOT NULL DEFAULT false,
    mismatch_detail   JSONB,
    model_version     VARCHAR(50)  NOT NULL,
    created_at        TIMESTAMP    NOT NULL DEFAULT now()
);

-- ============================================================
-- ad_embeddings
-- ============================================================
CREATE TABLE ad_embeddings (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ad_id      UUID REFERENCES ads(id),
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
    UNIQUE (ad_analysis_id, dimension)
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
    created_at         TIMESTAMP   NOT NULL DEFAULT now()
);

-- ============================================================
-- simulations
-- ============================================================
CREATE TABLE simulations (
    id                 UUID PRIMARY KEY,
    ad_id              UUID        NOT NULL REFERENCES ads(id),
    ad_analysis_id     UUID        NOT NULL REFERENCES ad_analyses(id),
    panel_id           UUID        NOT NULL REFERENCES panels(id),  -- ⚠️ NOT NULL
    organization_id    UUID        NOT NULL REFERENCES organizations(id),
    target_filter      JSONB,
    target_mode        VARCHAR(10) NOT NULL DEFAULT 'AUTO',
    sample_size        INTEGER     NOT NULL,
    qa_passed_count    INTEGER,
    low_sample_warning BOOLEAN     NOT NULL DEFAULT false,
    status             VARCHAR(20) NOT NULL DEFAULT 'QUEUED',  -- QUEUED | RUNNING | COMPLETED | FAILED
    model_version      VARCHAR(50) NOT NULL,                   -- ⚠️ NOT NULL, 기본값 없음
    error_detail       JSONB,
    created_by         UUID        NOT NULL REFERENCES users(id),
    started_at         TIMESTAMP,
    completed_at       TIMESTAMP,
    created_at         TIMESTAMP   NOT NULL DEFAULT now()
);
-- ⚠️ panel_id NOT NULL → 패널 없이 INSERT 불가. ALTER 필요 (하단 참고)
-- ⚠️ model_version NOT NULL, 기본값 없음 → INSERT 시 반드시 명시

-- ============================================================
-- persona_responses
-- ============================================================
CREATE TABLE persona_responses (
    id                  UUID PRIMARY KEY,
    simulation_id       UUID        NOT NULL REFERENCES simulations(id),
    persona_id          UUID        NOT NULL REFERENCES personas(id),
    exposure_context    VARCHAR(50),
    aisas               JSONB       NOT NULL,
    drop_stage          VARCHAR(20),
    drop_reason_tag     VARCHAR(50),
    purchase_intent     INTEGER     NOT NULL,
    trust               INTEGER     NOT NULL,
    rejected            BOOLEAN     NOT NULL DEFAULT false,
    rejection_reason_tag VARCHAR(50),
    emotion_tag         VARCHAR(50) NOT NULL,
    perceived_message   TEXT,
    perceived_target    VARCHAR(100),
    utterance           TEXT,
    qa_passed           BOOLEAN     NOT NULL,
    qa_fail_reason      VARCHAR(100),
    created_at          TIMESTAMP   NOT NULL DEFAULT now(),
    UNIQUE (simulation_id, persona_id)
);

-- ============================================================
-- simulation_aggregates
-- ============================================================
CREATE TABLE simulation_aggregates (
    id                  UUID PRIMARY KEY,
    simulation_id       UUID     NOT NULL UNIQUE REFERENCES simulations(id),
    click_intent_rate   NUMERIC  NOT NULL,
    ci_low              NUMERIC  NOT NULL,
    ci_high             NUMERIC  NOT NULL,
    purchase_intent_avg NUMERIC  NOT NULL,
    trust_avg           NUMERIC  NOT NULL,
    rejection_rate      NUMERIC  NOT NULL,
    variance_warning    BOOLEAN  NOT NULL DEFAULT false,
    payload             JSONB    NOT NULL,
    engine_version      VARCHAR(50) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT now()
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
    UNIQUE (simulation_id, dimension)
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
-- debate_sessions  [7.8]
-- ============================================================
CREATE TABLE debate_sessions (
    id            UUID PRIMARY KEY,
    simulation_id UUID        NOT NULL UNIQUE REFERENCES simulations(id),
    status        VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    ms_absent     BOOLEAN     NOT NULL DEFAULT false,
    llm_call_count INTEGER,
    model_version VARCHAR(50) NOT NULL,
    created_at    TIMESTAMP   NOT NULL DEFAULT now()
);

-- ============================================================
-- debate_statements  [7.8]
-- ============================================================
CREATE TABLE debate_statements (
    id            UUID PRIMARY KEY,
    session_id    UUID        NOT NULL REFERENCES debate_sessions(id),
    agent         VARCHAR(10) NOT NULL,
    round         INTEGER     NOT NULL,
    claim         TEXT        NOT NULL,
    targets_claim UUID REFERENCES debate_statements(id),
    evidence_refs JSONB       NOT NULL,
    verdict       VARCHAR(30),
    created_at    TIMESTAMP   NOT NULL DEFAULT now()
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
    UNIQUE (industry, metric)
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
-- ad_generations
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
    created_by            UUID REFERENCES users(id)
);

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
-- chat_sessions
-- ============================================================
CREATE TABLE chat_sessions (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id),
    messages   JSONB     DEFAULT '[]',
    created_at TIMESTAMP DEFAULT now()
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
```

---

## ORM 모델 vs 실제 DB 불일치 목록

| 테이블 | ORM 모델 컬럼 | 실제 DB 컬럼 | 비고 |
|---|---|---|---|
| `ads` | `ad_type` | `media_type` | 컬럼명 불일치 |
| `ads` | `s3_key` | `asset_url` | 컬럼명 불일치 |
| `ads` | `analysis` (JSONB) | 없음 | analysis는 ad_analyses 테이블로 분리됨 |
| `ads` | — | `copy_text, industry_category, product_category, ad_objective, target_filter, status, created_by, updated_at` | ORM에 없는 실제 컬럼 |
| `organizations` | `plan_type` | `plan` | 컬럼명 불일치 |
| `projects` | `organization_id, name, created_at` only | `+ description, status, created_by, updated_at` | ORM 미반영 |
| `simulations` | ORM 모델 없음 | 실제 존재 | Simulation ORM 모델 작성 필요 |

---

## ALTER TABLE — 코드 동작에 필요한 수정

현재 시뮬레이션 파이프라인이 `simulations` 테이블에 INSERT할 때 `panel_id`, `model_version` NOT NULL 제약으로 실패함.

```sql
-- 1. panel_id: 패널 시스템 미구현 상태이므로 nullable로 변경
ALTER TABLE simulations
    ALTER COLUMN panel_id DROP NOT NULL;

-- 2. model_version: 기본값 추가
ALTER TABLE simulations
    ALTER COLUMN model_version SET DEFAULT 'gpt-4o-mini';

-- 3. ads 테이블: 시뮬레이션 파이프라인이 임시 ads 행을 INSERT할 때 필요한 NOT NULL 컬럼들 nullable로 변경
ALTER TABLE ads
    ALTER COLUMN industry_category DROP NOT NULL,
    ALTER COLUMN product_category  DROP NOT NULL,
    ALTER COLUMN ad_objective      DROP NOT NULL,
    ALTER COLUMN created_by        DROP NOT NULL;
```

> 위 4개 ALTER를 실행하면 시뮬레이션 실행 → DB 저장 흐름이 정상 동작함.

---

## 관계도 (핵심)

```
organizations
└── organization_members → users
└── organization_subscriptions → subscription_plans
└── projects
    └── ads
        └── ad_analyses
            └── rubric_scores
        └── ad_embeddings
        └── simulations (organization_id도 직접 참조)
            └── persona_responses → personas → panels
            └── simulation_aggregates
            └── debate_sessions → debate_statements
            └── diagnoses → recommendations
            └── reports
        └── simulation_results (ad_id 직접 참조)
        └── simulation_comparisons
    └── ad_generations
        └── ad_generation_candidates
        └── ad_publish_logs
    └── chat_sessions
```

---

## 참고 문서

| 항목 | 위치 |
|---|---|
| API 엔드포인트 | `docs/api-spec.md` |
| ORM 모델 | `backend/core/models.py` |
| 시뮬레이션 서비스 | `backend/domain/simulation/service/simulation_service.py` |
| 제너레이터 서비스 | `backend/domain/generator/service/generator_service.py` |
