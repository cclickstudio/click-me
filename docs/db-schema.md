# ClickMe DB Schema

| Version | v4.2 |
|---|---|
| Date | 2026-07-09 |
| DB | NeonDB (PostgreSQL 18.4 + pgvector) |
| Source | ORM(`core/models.py` + `domain/simulation/models.py`) + Alembic 체인 대조 (구 v4.0 본문 SQL은 2026-06-18 `pg_dump` 실측) |

> v4.2 변경 (2026-07-09) — Alembic head를 실제 현행(`0011_inquiries_schema`)으로 정정하고, ORM(`core/models.py`)에 실재하는 테이블 기준으로 목록·괴리 섹션을 재정리. 아래 「본문 SQL」섹션은 2026-06-18 `pg_dump` 실측본이라 최신 ORM과 어긋나는 부분이 있으므로, 정본은 ORM(`core/models.py`·`domain/simulation/models.py`)·Alembic이다.
>
> v4.0 변경 — 실 DB를 pg_dump로 전량 재추출. 테이블 30 → **45개**, ENUM 타입 10종 명시.
> 변경: `users` `email`→`login_id`, `team_id`·`phone_num`·`user_email`·`must_change_password` 추가 / 여러 테이블에 `deleted_at` 소프트삭제 컬럼 추가.
>
> **admin 소프트삭제** — 조직/유저 삭제는 hard delete가 아니라 `status='INACTIVE'`(+ Cognito disable)로 처리해 데이터는 보존한다. 복원 시 `status='ACTIVE'`, 영구삭제(purge) 시에만 행을 실제로 지운다. auth 미들웨어가 `status != 'ACTIVE'`면 401 차단.
>
> **Alembic 체인(현행, head = `0011_inquiries_schema`)** — 완전 선형:
> `0001_baseline`(구 001~029 squash) → `0002_persona_weight` → `0003_categories_kinds` → `0004_generator_kb_search_vector` → `0005_rename_memory_tables`(2026-07-03) → `0006_management_notifications` → `0007_ads_generation_id` → `0008_chat_sessions_created_by` → `0009_center_suggestions` → `0010_management_approval_records` → `0011_inquiries_schema`(2026-07-08).
> 구 3자리 리비전(001/002…)은 제거됨. 새 DB는 `0001_baseline`이 대부분의 스키마를 create_all로 한 번에 생성하고 0002 이후는 증분.
>
> **마이그레이션 0005·0006 요약**
> - `0005_rename_memory_tables`(2026-07-03 적용): `chat_long_term_memory`→`chat_session_summaries` · `execution_history`→`chat_execution_history` 개명, `management_user_memory` drop, `automation_runs` 신설.
> - `0006_management_notifications`: `management_notifications` 신설.
>   (이전 문서는 이 두 리비전 번호를 서로 뒤바꿔 「0004 → 0006 → 0005」라 적었으나, 실제 파일 기준 순서는 `0004 → 0005_rename → 0006_notifications`이다.)
> - 매니지먼트(4-2) 표에 ORM 기준 테이블 목록 덧붙임 — 아래 §매니지먼트 참조.

---

## 테이블 목록

> **범례** — ✅ = ORM(`core/models.py` 또는 `domain/simulation/models.py`)에 실재하는 테이블. ⏸ = 문서/구 스키마엔 있으나 **현재 ORM에 매핑 없음**(계획 단계·미구현이거나 옛 세대 잔존 테이블). 실 DB(6/24 스냅샷 introspection)엔 물리적으로 남아 있을 수 있으나 코드가 쓰지 않는다.

### 인증 · 사용자
| 테이블 | 상태 | 역할 |
|---|---|---|
| `users` | ✅ | 사용자 (로그인 ID = `login_id`, 비밀번호는 Cognito 관리 → ORM에 `password_hash` 없음) |
| `teams` | ✅ | 팀 (조직 하위 협업 단위) |
| `refresh_tokens` | ⏸ | JWT 리프레시 토큰 — local JWT 모드 대비 계획, ORM 미매핑(미구현) |
| `user_settings` | ⏸ | 사용자별 설정(테마·알림) — ORM 미매핑(미구현) |
| `audit_logs` | ⏸ | 사용자 행위 감사 로그 — ORM 미매핑(미구현). 매니지먼트 감사는 `management_audit_events` 사용 |

### 조직 · 빌링
| 테이블 | 상태 | 역할 |
|---|---|---|
| `organizations` | ✅ | 기업(빌링 단위). 플랜은 별도 테이블이 아니라 `organizations.plan` VARCHAR(`free`\|`professional`\|`enterprise`) |
| `organization_members` | ✅ | 기업-사용자 매핑 |
| `organization_subscriptions` | ⏸ | 기업 구독 — ORM 미매핑(미구현, 플랜은 `organizations.plan` 컬럼으로 대체) |
| `subscription_plans` | ⏸ | 구독 플랜 정의 — ORM 미매핑(미구현) |
| `project_members` | ⏸ | 프로젝트 협업 멤버(뷰어/에디터/오너, ENUM `project_member_role`) — **계획됐으나 ORM 미매핑(미구현, 실 DB 비어있음)** |

### 프로젝트 · 광고
| 테이블 | 상태 | 역할 |
|---|---|---|
| `projects` | ✅ | 프로젝트(캠페인 단위) |
| `ads` | ✅ | 광고 소재 (`generation_id` 느슨 참조 — 0007) |
| `ad_analyses` | ✅ | 광고 분석 결과 (시뮬 SimBase) |
| `ad_embeddings` | ⏸ | 광고 벡터 임베딩 — ORM 미매핑(미구현) |
| `rubric_scores` | ✅ | 광고 루브릭 점수 (시뮬 SimBase) |

### 시뮬레이션 (4-1)
| 테이블 | 상태 | 역할 |
|---|---|---|
| `panels` | ✅ | 페르소나 패널 (SimBase) |
| `personas` | ✅ | 개별 페르소나 (SimBase) |
| `persona_templates` | ⏸ | 페르소나 템플릿(클러스터·임베딩) — ORM 미매핑(미구현) |
| `simulations` | ✅ | 시뮬레이션 실행 단위 (SimBase, 소프트삭제 `deleted_at`) |
| `persona_responses` | ✅ | 페르소나별 반응 (SimBase, ORM 클래스명 `PersonaReaction`) |
| `simulation_aggregates` | ✅ | 시뮬레이션 집계 결과 (SimBase, `brand_recognition_rate` 포함) |
| `simulation_results` | ⏸ | 시뮬레이션 결과(분포/페르소나, 임시) — ORM 미매핑(미구현) |
| `simulation_comparisons` | ⏸ | A/B 비교 — ORM 미매핑(미구현) |
| `diagnoses` | ⏸ | 시뮬레이션 진단 — ORM 미매핑(미구현) |
| `recommendations` | ⏸ | 개선 추천 — ORM 미매핑(미구현) |
| `reports` | ⏸ | PDF 리포트 — ORM 미매핑(미구현, 리포트는 런타임 생성) |

### KB / RAG 청크 (도메인별)
| 테이블 | 상태 | 역할 |
|---|---|---|
| `simulation_kb_chunks` | ✅ | 시뮬 KB 청크(벡터) |
| `generator_kb_chunks` | ✅ | 제너레이터 KB 청크(벡터 + FTS `search_vector` — 0004) |
| `clio_kb_chunks` | ✅ | CLIO 광고 일반지식 KB 청크(벡터) |

### 페르소나 토론
| 테이블 | 상태 | 역할 |
|---|---|---|
| `persona_debates` | ✅ | 페르소나 토론 세션 (simulations 1:N) |
| `persona_debate_participants` | ✅ | 토론 패널 |
| `persona_debate_utterances` | ✅ | 토론 발언 로그(라운드×패널) |

### 광고 생성 (4-3) · 게시
| 테이블 | 상태 | 역할 |
|---|---|---|
| `ad_generations` | ✅ | 광고 제너레이터 실행 |
| `ad_generation_candidates` | ✅ | 제너레이터 후보 |
| `ad_publish_logs` | ✅ | 광고 게시 이력(IG) |
| `ad_campaign_logs` | ✅ | Meta Marketing API 집행 이력 |
| `generated_ads` | ⏸ | 생성 이미지 광고(독립 저장, ENUM `ad_status`) — ORM 미매핑(미구현) |
| `brand_profiles` | ✅ | 클라이언트 브랜드 프로필(`client_id` PK) |
| `brand_kits` | ✅ | 조직 단위 브랜드 키트(색·로고·톤 명명 저장) |
| `ad_templates` | ✅ | 시뮬/생성 입력 명명 저장 템플릿(sim\|gen) |

### 매니지먼트 (4-2)
| 테이블 | 역할 |
|---|---|
| `management_notifications` | 이상 감지 운영 알림(하이브리드 C안) — 채팅과 분리 저장, org·kind·dedup_key 미해결 1행 |
| `management_created_campaigns` | 우리가 생성한 캠페인 레지스트리(org 귀속, 소프트 삭제, 시뮬 연결 키) — 덧붙임 07-06 |
| `management_idempotency_keys` | 실행 멱등키 — 동일 승인 건 중복 집행 차단 — 덧붙임 07-06 |
| `management_audit_events` | 실행 감사 로그(승인→실행 연결) — 덧붙임 07-06 |
| `management_approval_records` | 승인 원장 — 서버 발행 승인의 진위 대조, 집행 게이트 #5 — 마이그 0010 |
| `management_meta_connections` | org별 Meta OAuth 연결(토큰 암호화 저장) — 덧붙임 07-06 |
| `management_campaign_kpi_overrides` | 캠페인별 KPI 목표(target_roas 등) 덮어쓰기 — 덧붙임 07-06 |
| `management_kb_documents` / `_kb_chunks` / `_kb_feedback` / `_kb_eval_cases` | 어시스턴트(CLIO) RAG 지식베이스·평가 — 덧붙임 07-06 |
| `management_chat_sessions` / `_chat_messages` / `management_agent_runs` | 어시스턴트 전용 대화·에이전트 실행 기록 — 덧붙임 07-06 |
| `automation_runs` | APScheduler 워커 결과 공용 저장소(3도메인, dedup 부분 유니크) — 0005 신설 |
| `chat_execution_history` | 실행 확정 이력 = 채팅 에이전트 롱텀 메모리 — 0005에서 `execution_history` 개명 |

> 모두 ✅ ORM 매핑됨. 반면 옛 세대 매니지먼트 실행 테이블(`action_proposals`·`approvals`·`execution_runs`·`idempotency_keys`·`audit_events`·`remediation_escalations`·`created_campaigns`·`campaign_kpi_overrides`·`meta_connections`)은 ⏸ — 현 ORM은 `management_` 프리픽스 이름(`management_idempotency_keys`·`management_audit_events`·`management_created_campaigns`·`management_campaign_kpi_overrides`·`management_meta_connections`)만 쓰고, 제안·승인 원장은 `management_approval_records`로 일원화됐다(구 `action_proposals`·`approvals`·`execution_runs`는 현 ORM에 없음).

### 채팅 (4-4) · 센터
| 테이블 | 상태 | 역할 |
|---|---|---|
| `chat_sessions` | ✅ | 채팅 세션 (제목·`created_by`·`last_read_at`. 메시지는 `chat_messages`로 정규화 — 구 `messages` JSONB 컬럼 폐기) |
| `chat_messages` | ✅ | 채팅 메시지(user\|assistant, ENUM `chat_role`, `metadata` JSONB) |
| `chat_session_summaries` | ✅ | 세션 요약(숏텀 압축, 임베딩). 구 `chat_long_term_memory` 개명 — 0005 |
| `chat_execution_history` | ✅ | 실행 이력 롱텀 메모리(tsvector BM25). 구 `execution_history` 개명 — 0005 |
| `chat_brand_profiles` | ✅ | 프로젝트별 브랜드 톤·타겟 기억(project_id UNIQUE) |
| `center_suggestions` | ✅ | 센터(우측 통합 알림) 크로스도메인 제안 — 0009 신설. 알림 센터가 `management_notifications`와 병합 조회 |

### 결제 · 크레딧
| 테이블 | 상태 | 역할 |
|---|---|---|
| `payment_orders` | ✅ | Toss 크레딧 충전 주문(서버 기억 금액·승인 상태) |
| `credit_ledger` | ✅ | 크레딧 원장(append-only, 잔액 = delta 합) |

### 참조 · 기타
| 테이블 | 상태 | 역할 |
|---|---|---|
| `benchmarks` | ⏸ | 업종별 벤치마크 — ORM 미매핑(미구현) |
| `rag_chunks` | ⏸ | RAG 청크(구 단일 테이블) — ORM 미매핑(도메인별 `*_kb_chunks`로 대체) |
| `calibration_data` | ⏸ | 예측↔실측 캘리브레이션 데이터 — ORM 미매핑(미구현, calibration 해금 전) |
| `kinds` | ✅* | NICE 상품/서비스 분류 45류 — 0003 마이그로 생성(ORM 클래스 없이 SQL 관리) |
| `categories` | ✅* | 업종 카테고리 묶음 — 0003 |
| `category_kinds` | ✅* | 카테고리↔류 매핑(다대다) — 0003 |
| `inquiries` | ✅ | 고객 문의 — **0011에서 재정의**(구 `name`/`email`/`message` → `title`/`content`/`contact_email`/`is_resolved`/`resolved_at`) |
| `alembic_version` | — | Alembic 마이그레이션 버전(스탬프) |

> `✅*` = ORM `core/models.py`에 클래스는 없지만 Alembic 0003으로 생성·운영되는 참조 테이블.

---

## ENUM 타입 (10종)

> DB에 타입은 정의돼 있으나, 대부분의 테이블은 `VARCHAR + 앱 레벨 검증`을 사용한다.
> ENUM 컬럼은 DB에 `generated_ads.status`(ad_status) · `chat_messages.role`(chat_role) · `project_members.role`(project_member_role) 셋뿐이며, 이 중 현 ORM이 실제로 매핑·사용하는 것은 **`chat_messages.role`(chat_role)** 하나다(나머지 두 테이블은 ⏸ ORM 미매핑).

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
    password_hash        VARCHAR(255) NOT NULL,           -- ⚠️ 구 실측 컬럼. 현 ORM(User)엔 미매핑 — 비밀번호는 Cognito 관리(local JWT 대비 잔존 가능)
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
    brand_recognized     BOOLEAN       NOT NULL DEFAULT false,  -- ORM 추가(6/18 실측엔 없음)
    perceived_brand      VARCHAR(200),                          -- ORM 추가
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
    brand_recognition_rate NUMERIC    NOT NULL DEFAULT 0.0,  -- ORM 추가(6/18 실측엔 없음)
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
    created_by UUID REFERENCES users(id),   -- 세션 개시자(실행자) — 0007 마이그레이션, 내역 표시용
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
-- inquiries  (⚠️ 0011에서 재정의됨 — 아래는 현행 스키마, 구 name/email/message 폐기)
-- ============================================================
CREATE TABLE inquiries (
    id            UUID PRIMARY KEY,
    title         VARCHAR(300) NOT NULL,
    content       TEXT         NOT NULL,
    contact_email VARCHAR(255),                       -- 회신 연락처
    is_resolved   BOOLEAN      NOT NULL DEFAULT false, -- 관리자 해결 처리
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    resolved_at   TIMESTAMPTZ
);
CREATE INDEX ix_inquiries_created_at ON inquiries (created_at DESC);

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
-- management_approval_records  (승인 원장, 집행 게이트 #5 — 마이그 0010)
-- 서버가 발행한 승인만 집행되게 하는 진위 대조 원본.
-- 집행기는 approval_id로 이 표를 조회해 proposal_hash·expires_at·consumed_at을 검증한다.
-- ============================================================
CREATE TABLE management_approval_records (
    approval_id               VARCHAR(64)  PRIMARY KEY,
    proposal_id               VARCHAR(64)  NOT NULL,
    proposal_hash             VARCHAR(64)  NOT NULL,
    tenant_id                 VARCHAR(64)  NOT NULL,
    approver_id               VARCHAR(64)  NOT NULL,
    action_tier               INTEGER      NOT NULL,            -- ActionTier(IntEnum) 값
    execution_mode            VARCHAR(16)  NOT NULL,            -- ExecutionMode.value
    approval_policy_version   VARCHAR(64)  NOT NULL,
    expected_state_version    VARCHAR(64)  NOT NULL,
    approved_at               TIMESTAMPTZ  NOT NULL,
    expires_at                TIMESTAMPTZ  NOT NULL,
    consumed_at               TIMESTAMPTZ,                      -- 집행 성공 시 마킹 (nullable)
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_mgmt_approval_proposal ON management_approval_records (proposal_id);
CREATE INDEX ix_mgmt_approval_tenant   ON management_approval_records (tenant_id);

-- ============================================================
-- alembic_version  (마이그레이션 버전 추적)
-- ============================================================
CREATE TABLE alembic_version (
    version_num VARCHAR(32) PRIMARY KEY
);
```

---

## ORM 모델 vs 실제 DB (2026-07-09 재정리)

> ORM은 두 곳에 나뉜다. **`core/models.py`**(auth·조직·프로젝트·광고·생성·매니지먼트·채팅·결제·센터)와 **`domain/simulation/models.py`**(시뮬 전용 `SimBase` — `panels`·`personas`·`ad_analyses`·`simulations`·`persona_responses`·`rubric_scores`·`simulation_aggregates`). 시뮬 핵심 테이블은 `core`엔 없고 도메인 로컬 Base로 격리돼 있다(추후 병합 예정). 아래 "DB에 있음, ORM 없음"은 이 둘 어디에도 클래스가 없는 것만 가리킨다.

| 구분 | 내용 |
|---|---|
| **DB에 있음, ORM(어느 Base에도) 없음 — ⏸ 미구현/계획/구세대** | `refresh_tokens`·`user_settings`·`audit_logs`·`organization_subscriptions`·`subscription_plans`·`project_members`·`ad_embeddings`·`persona_templates`·`simulation_results`·`simulation_comparisons`·`diagnoses`·`recommendations`·`reports`·`benchmarks`·`rag_chunks`·`calibration_data`·`generated_ads` · (구세대 매니지먼트) `action_proposals`·`approvals`·`execution_runs`·`idempotency_keys`·`audit_events`·`remediation_escalations`·`created_campaigns`·`campaign_kpi_overrides`·`meta_connections` · (SQL 관리) `kinds`·`categories`·`category_kinds`·`alembic_version` · (LangGraph 라이브러리) `checkpoints`·`checkpoint_blobs`·`checkpoint_writes`·`checkpoint_migrations` |
| **ORM에 선언, 6/24 덤프엔 없음(이후 추가)** | `brand_kits`·`ad_templates`·`clio_kb_chunks`·`chat_session_summaries`(구 `chat_long_term_memory`)·`chat_execution_history`(구 `execution_history`)·`chat_brand_profiles`·`center_suggestions`·`payment_orders`·`credit_ledger`·`automation_runs`·`management_notifications`·`management_approval_records`·`management_meta_connections`·`management_campaign_kpi_overrides`·`management_created_campaigns`·`management_idempotency_keys`·`management_audit_events` |
| `users` | ORM(`User`)엔 **`password_hash` 없음** — 비밀번호는 Cognito 관리. 구 실측 SQL의 `password_hash NOT NULL`은 local JWT 대비 잔존 컬럼일 수 있다. |
| `ads` | 현 ORM은 실측과 정합(`media_type`/`asset_url`/`copy_text`/`industry_category`/`product_category`/`ad_objective`/`target_filter`/`status`/`created_by`/`updated_at`) + **0007에서 `generation_id` 추가**(cross-base 느슨 참조). |
| `projects` | 현 ORM에 `description`·`status`·`created_by`·`updated_at`·`deleted_at`·`team_id` 전부 반영(정합). |
| `inquiries` | **0011에서 재정의** — ORM(`Inquiry`)·DB 모두 `title`/`content`/`contact_email`/`is_resolved`/`created_at`/`resolved_at`. 구 `name`/`email`/`message`는 폐기. |

> **매니지먼트 실행 계열 — 이름 두 세대**
>
> 같은 역할의 테이블이 이름 세대 두 개로 존재한다. 현 ORM은 신명(`management_` prefix)만 사용한다.
>
> | 구명 (옛 세대, ⏸ ORM 미매핑) | 신명 (현재 ORM ✅) |
> |---|---|
> | `idempotency_keys` | `management_idempotency_keys` |
> | `audit_events` | `management_audit_events` |
> | `created_campaigns` | `management_created_campaigns` |
> | `campaign_kpi_overrides` | `management_campaign_kpi_overrides` |
> | `meta_connections` | `management_meta_connections` |
> | `action_proposals` · `approvals` · `execution_runs` | (제안·승인은 `management_approval_records` 원장으로 일원화 — 구 3종은 현 ORM에 없음) |
>
> 경위 — ① 초기 구 마이그레이션이 구명 테이블을 생성했고, 6/24 실DB introspection(`db-erd.md`)엔 그래서 구명이 찍혀 있다(`idempotency_keys` 12행 등). ② 이후 ORM이 `management_` prefix 신명으로 정리됐고 구 마이그은 삭제·재편입됐다. ③ 빈 DB는 `0001_baseline`의 create_all이 신명으로 바로 생성하지만, 기존 DB엔 구명 테이블이 물리적으로 남아 있을 수 있다.
>
> 할 일 — `pg_dump --schema-only`를 다시 떠서 ⑴ 구명 테이블이 아직 남았는지 ⑵ 신명 테이블이 생성돼 있는지 확인하고, 결과로 위 표를 확정 정리한다.

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
