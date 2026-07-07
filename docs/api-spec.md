# ClickMe API Specification

| Version | v2.1 |
|---|---|
| Date | 2026-07-03 |
| Base URL | `http://localhost:8000/api` (dev) |
| Content-Type | `application/json` |

---

## 1. Authentication

인증 방식은 `AUTH_PROVIDER` 설정으로 결정된다.

- **운영: AWS Cognito** (`AUTH_PROVIDER=cognito`). 프론트가 Cognito User Pool로 로그인하고, 백엔드는 ID/Access 토큰을 **RS256 + JWKS**로 검증(`core/auth.py`). 토큰은 `Authorization: Bearer <token>` 헤더 또는 `access_token` 쿠키로 전달. 역할은 `cognito:groups`(ADMIN/COMPANY/USER)에서 판별. Cognito username = `login_id`.
- **로컬 기본: 자체 JWT** (`AUTH_PROVIDER=local`). HS256으로 직접 발급·검증.
- **계정 상태 차단** — 사용자 `status != ACTIVE`(예: 관리자 소프트 삭제로 `INACTIVE`)면 인증 미들웨어가 **401**을 반환.
- **역할** ADMIN / COMPANY / USER. 관리자 API는 경로 프리픽스 `/api/admin/*` + ADMIN 역할로 제한.

> 계정은 자가가입·소셜 로그인이 없으며 **관리자가 직접 생성**한다. 발급 계정은 최초 로그인 시 비밀번호 변경을 유도(`must_change_password`).

---

## 2. Ad Analysis

### POST /api/analyze/image

Analyze an image ad.

**Request Body**
```json
{
  "ad_id": "string",
  "image_url": "string (S3 presigned URL)",
  "prompt_version": "v1.0"
}
```

**Response 200**
```json
{
  "ad_id": "string",
  "confidence": 0.85,
  "text_analysis": {
    "headline": "string | null",
    "sub_headline": "string | null",
    "body": "string | null",
    "cta": "string | null",
    "usp_extracted": ["string"],
    "emotional_keywords": ["string"]
  },
  "visual_analysis": {
    "dominant_colors": ["string"],
    "emotional_tone": "string | null",
    "layout_type": "string | null",
    "brand_elements": ["string"]
  },
  "strategic_analysis": {
    "target_demographic": "string | null",
    "purchase_stage_target": "awareness | consideration | conversion",
    "usp": "string | null",
    "key_message": "string | null",
    "likely_resonates_with": ["string"],
    "likely_resists_with": ["string"],
    "potential_objections": ["string"]
  }
}
```

---

### POST /api/analyze/text

Analyze a text ad.

**Request Body**
```json
{
  "ad_id": "string",
  "text_content": {
    "headline": "string",
    "body": "string",
    "cta": "string"
  }
}
```

**Response 200**: Same structure as `/api/analyze/image` (`visual_analysis: null`).

---

### POST /api/analyze/upload

Upload file to S3 and return ad_id.

**Request**: `multipart/form-data`
- `file`: image file (JPG/PNG/WebP/GIF, max 10MB)
- `project_id`: string

**Response 200**
```json
{
  "ad_id": "string",
  "s3_url": "string",
  "presigned_url": "string (valid 1 hour)"
}
```

---

## 3. Persona Generation

### POST /api/personas/generate

Generate OCEAN 4-layer personas.

**Request Body**
```json
{
  "simulation_id": "string",
  "count": 20,
  "segment_distribution": {
    "20s_male_student": 0.10,
    "30s_female_working": 0.20
  },
  "ad_category": "string | null"
}
```

**Response 200**
```json
{
  "simulation_id": "string",
  "personas": [
    {
      "persona_id": "P_0001",
      "segment": "30s_female_working",
      "ocean": {
        "openness": 0.72,
        "conscientiousness": 0.61,
        "extraversion": 0.45,
        "agreeableness": 0.58,
        "neuroticism": 0.33
      },
      "attributes": {
        "age": 32,
        "gender": "female",
        "region": "Seoul Gangnam",
        "occupation": "marketer",
        "income_level": "upper-middle",
        "education": "bachelor",
        "purchase_motivation": "practicality",
        "price_sensitivity": 0.4,
        "brand_loyalty": 0.6,
        "trigger_words": ["discount", "review"],
        "rejection_words": ["promotional"],
        "current_emotion": "tired after work"
      },
      "temperature": 0.75,
      "seed": 4821
    }
  ]
}
```

---

## 4. Simulation

### POST /api/simulate/reactions

Start async simulation task. Runs in-process (asyncio) and returns immediately.

**Request Body**
```json
{
  "simulation_id": "string",
  "ad_analysis": { },
  "personas": [ ],
  "objective": "conversion",
  "persona_set": {
    "id": "string",
    "size": 20,
    "composition": { "30s_female_working": 0.2 }
  }
}
```

**Response 200**
```json
{
  "task_id": "uuid",
  "stream_url": "/api/simulate/{task_id}/stream"
}
```

---

### GET /api/simulate/{task_id}/stream

SSE streaming. Real-time simulation progress events.

**Response**: `text/event-stream`

```
data: {"event": "progress", "stage": "persona_factory", "pct": 15, "message": "Generating personas"}

data: {"event": "progress", "stage": "exposure", "pct": 40, "message": "Simulating reactions (8/20)"}

data: {"event": "progress", "stage": "scoring", "pct": 70, "message": "SSR scoring complete"}

data: {"event": "milestone", "message": "Aggregation complete"}

data: {"event": "completed", "result_url": "/api/simulate/{task_id}/result"}
```

---

### GET /api/simulate/{task_id}/result

Retrieve completed simulation result.

**Response 200**
```json
{
  "simulation_id": "string",
  "task_id": "string",
  "status": "completed",
  "p0": {
    "persona_reactions": [
      {
        "persona_id": "P_0001",
        "free_text_reaction": "string",
        "purchase_intent_distribution": [0.05, 0.10, 0.25, 0.40, 0.20]
      }
    ],
    "aggregate_purchase_intent": [0.08, 0.15, 0.30, 0.32, 0.15],
    "kobaco_comparable": true
  },
  "p1": {
    "signal_distributions": {
      "attention": {"mean": 0.62, "std": 0.11, "p10": 0.47, "p90": 0.78, "raw_probs": []},
      "sentiment": {"mean": 0.18, "std": 0.19, "p10": -0.08, "p90": 0.44, "raw_probs": []},
      "click_intent": {"mean": 0.58, "std": 0.14, "raw_probs": []},
      "comprehension": {"mean": 0.71, "std": 0.09, "raw_probs": []},
      "recall": {"mean": 0.55, "std": 0.13, "raw_probs": []}
    },
    "kpi": {
      "ctr": 0.42,
      "cvr": 0.18,
      "net_sentiment": 0.31
    },
    "funnel": {
      "attention": 0.85,
      "comprehension": 0.62,
      "click": 0.42,
      "conversion": 0.18
    },
    "langsmith_trace_url": "string | null",
    "note": "P1 signals are exploratory. No human ground truth."
  }
}
```

---

### (구현 현황) /api/simulation/* — 실제 라우터

> 위 `/api/simulate/*`는 초기 초안. **실제 구현은 `/api/simulation/*`** 이며 아래가 현재 동작.

#### POST /api/simulation/run

동기 실행 — 광고(multipart/form-data) 입력 → 끝까지 돌려 **반응·루브릭·집계 + DB 저장**을 한 번에 반환. 별도 조회 호출 불필요.

- **Query** `shape=full`(기본, 원본 전체) \| `shape=analysis`(분석팀 정리 스키마).
- **정리 스키마**(`shape=analysis`) = 중복 제거·평탄화: `meta`(run_id·simulation_id·source·model_version) / `ad` / `ad_analysis`(detected_*·ad_features·`alignment[]`) / `simulation` / `personas`(consumption 5키 고정·`_source` 제거) / `reactions` / `aggregate`(8필드). 변환 로직 `domain/simulation/service/analysis_view.py`.
- **run_id 출처** — 이 응답의 `meta.run_id`(정리) 또는 최상위 `run_id`(원본). 비동기 `POST /api/simulation`(start)은 `{run_id, result_url}` 반환.

#### GET /api/simulation/{run_id}/result/analysis

이미 끝난 런(동기/비동기 무관)을 **정리 스키마로 재조회**. 미완료/없음이면 404. 동기 `run?shape=analysis`로 받았으면 호출 불필요(보조 경로).

> 참고: `ad.asset_url`은 스토리지(S3) 연동 전까지 로컬/None — 인프라 작업 별도.

---

### POST /api/simulate/debate

Run Debate Agent. [Target: 7.8]

**Response 501**
```json
{"detail": "Debate Agent is a 7.8 target feature."}
```

---

## 5. Chat

### POST /api/chat/complete

Chat assistant response (SSE streaming).

**Request Body**
```json
{
  "session_id": "string",
  "messages": [
    {"role": "user", "content": "string"},
    {"role": "assistant", "content": "string"}
  ],
  "context_ad_id": "string | null",
  "context_simulation_id": "string | null"
}
```

**Response**: `text/event-stream`
```
data: {"token": "This"}
data: {"token": " ad's"}
data: {"token": " attention score"}
data: {"done": true}
```

---

### GET /api/chat/sessions

List chat sessions.

**Response 200**
```json
{
  "sessions": [
    {
      "session_id": "string",
      "created_at": "ISO8601",
      "last_message_at": "ISO8601",
      "message_count": 12,
      "title": "string (first message summary)"
    }
  ]
}
```

---

### GET /api/chat/sessions/{session_id}/messages

Messages in a specific session.

**Response 200**
```json
{
  "session_id": "string",
  "messages": [
    {
      "message_id": "string",
      "role": "user | assistant",
      "content": "string",
      "created_at": "ISO8601"
    }
  ]
}
```

---

## 6. Inquiries

### POST /api/inquiries

Submit an inquiry.

**Request Body**
```json
{
  "title": "string",
  "content": "string",
  "contact_email": "string | null"
}
```

**Response 201**
```json
{"inquiry_id": "string", "created_at": "ISO8601"}
```

---

## 7. Admin API

> 경로 프리픽스 `/admin/*` + ADMIN 역할로 제한. 계정 매핑: Cognito username = `login_id`,
> role → 동명 그룹(ADMIN/COMPANY/USER). `AUTH_PROVIDER=local`이면 Cognito 동기화는 no-op.

**삭제 정책** — 기본 삭제(`DELETE`)는 **소프트 삭제**다. DB는 `status=INACTIVE`로 두고 Cognito 계정은
`disable`(삭제 아님)해 로그인만 차단한다. 데이터(프로젝트·시뮬·제너·채팅)는 사후 조회용으로 보존된다.
`restore`로 되살리고, `purge`로만 영구(하드) 삭제한다.

### 조직(회사)

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/admin/organizations` | 조직 목록(프로젝트 0개 회사 포함) |
| DELETE | `/api/admin/companies/{org_id}` | 소프트 삭제 — 조직·소속 유저 `INACTIVE` + Cognito disable |
| POST | `/api/admin/companies/{org_id}/restore` | 복원 — 조직·소속 유저 `ACTIVE` + Cognito enable(없으면 재생성) |
| DELETE | `/api/admin/companies/{org_id}/purge` | 영구 삭제 — Cognito + DB(조직·멤버·유저) + 하위 프로젝트/시뮬/제너/채팅 하드 삭제 |

**GET /api/admin/organizations** — 쿼리: `limit`(기본 20, 최대 200) · `offset`(기본 0) ·
`sort`(`name|created_at|status`, 기본 `created_at`) · `order`(`asc|desc`, 기본 `desc`).

**Response 200** — `[{ "id", "name", "status": "ACTIVE|INACTIVE", "created_at" }]`

`restore`·`purge`·`delete` 응답은 모두 `{"ok": true}`. 조직 없음 → 404.

### 유저

| Method | Path | 설명 |
| --- | --- | --- |
| GET | `/api/admin/users` | 유저 목록 |
| POST | `/api/admin/users` | 계정 생성(ADMIN/COMPANY/USER) |
| PATCH | `/api/admin/users/{user_id}` | 이름·비밀번호 수정 |
| DELETE | `/api/admin/users/{user_id}` | 소프트 삭제 — `INACTIVE` + Cognito disable |
| POST | `/api/admin/users/{user_id}/restore` | 복원 — `ACTIVE` + Cognito enable(없으면 재생성) |
| DELETE | `/api/admin/users/{user_id}/purge` | 영구 삭제 — Cognito + DB(유저·멤버십) + 본인 생성 프로젝트/시뮬/제너/채팅 하드 삭제 |

**GET /api/admin/users** — 쿼리: `limit`(기본 20, 최대 200) · `offset`(기본 0) ·
`sort`(`role|name|created_at|status`, 기본 `role`) · `order`(`asc|desc`) · `role`(`ADMIN|COMPANY|USER` 필터).
`sort` 미지정(기본 `role`) 시 **ADMIN→COMPANY→USER** 우선순위 정렬.

**Response 200** — `[{ "id", "login_id", "name", "role", "status", "created_at", "organization_name" }]`

**POST /api/admin/users** — Body: `{ "name", "login_id", "password"(≥8), "role", "company_name"?(role=COMPANY),
"organization_id"?(role=USER) }`. 201 → UserRow. 아이디 중복 409, 비번 짧음/역할 오류 400.

**주의** — `delete`/`purge`는 본인 계정 불가(400). `COMPANY` 계정의 개별 `delete`/`purge`는 막고
'조직 삭제/영구삭제'로 회사째 처리하도록 유도(400).

### 내역 조회 (시뮬·제너·채팅)

| Method | Path |
| --- | --- |
| GET | `/api/admin/simulations` |
| GET | `/api/admin/generations` |
| GET | `/api/admin/chats` |

공통 쿼리: `limit`(기본 20, 최대 200) · `offset` · `sort`(`created_at|title|org_name`) · `order` ·
`search_field`(`title|org_name`) · `search` · `X-Org-Id` 헤더(특정 조직 필터) ·
**`org_status`**(`ACTIVE|INACTIVE` — 소속 조직 상태 필터). 시뮬·제너는 추가로
`status`(`completed|in_progress|failed`) 버킷 필터.

응답 각 행에 **`org_status`**(소속 조직 상태) 포함 — 삭제된(INACTIVE) 조직의 내역을 화면에서 구분·필터.

---

## 8. Ad Generator

생성모드 광고 파이프라인 — 상품 분석 → 전략 3종 → 템플릿 선택 → 후보 3종 이미지 생성 → QA → 생성 이유.

### POST /api/generator/generations

Start async ad generation task. Runs LangGraph pipeline in background.

**Request Body**
```json
{
  "project_id": "uuid | null",
  "product_name": "string",
  "product_description": "string",
  "target_audience": "string",
  "campaign_objective": "conversion",
  "brand_color": "#3182F6 | null",
  "brand_logo_url": "string | null",
  "tone_and_manner": "string | null",
  "width": 1080,
  "height": 1080
}
```

`campaign_objective`: `awareness | conversion | lead_gen | app_install | retention | product_launch | promotion`

**Response 200**
```json
{
  "generation_id": "uuid",
  "stream_url": "/api/generator/generations/{generation_id}/stream"
}
```

---

### GET /api/generator/generations/{generation_id}/stream

SSE streaming. Real-time generation progress events.

**Response**: `text/event-stream`

```
data: {"event": "progress", "stage": "product_analysis", "pct": 10, "message": "상품 분석 중"}

data: {"event": "progress", "stage": "strategy", "pct": 25, "message": "광고 전략 생성 중"}

data: {"event": "progress", "stage": "template", "pct": 35, "message": "템플릿 선택 중"}

data: {"event": "progress", "stage": "candidates", "pct": 55, "message": "광고 이미지 생성 중 (2/3)"}

data: {"event": "progress", "stage": "qa", "pct": 85, "message": "품질 검증 중"}

data: {"event": "progress", "stage": "explain", "pct": 95, "message": "생성 이유 작성 중"}

data: {"event": "completed", "result_url": "/api/generator/generations/{generation_id}"}
```

---

### GET /api/generator/generations/{generation_id}

Retrieve completed generation result (candidates, QA, explanations, presigned image URLs).

**Response 200**
```json
{
  "generation_id": "uuid",
  "status": "pending | running | completed | failed",
  "input": { },
  "product_analysis": {
    "core_values": ["string"],
    "pain_points": ["string"],
    "benefits": ["string"]
  },
  "strategies": [
    {"strategy_type": "benefit", "name": "string", "key_message": "string", "rationale": "string"}
  ],
  "selected_candidate_id": "uuid | null",
  "error_message": "string | null",
  "created_at": "ISO8601",
  "candidates": [
    {
      "candidate_id": "uuid",
      "idx": 0,
      "strategy": { "strategy_type": "benefit", "name": "string", "key_message": "string", "rationale": "string" },
      "template_id": "A | B | C",
      "copy": {
        "headline": "string",
        "subcopy": "string",
        "benefit_text": "string",
        "cta": "string"
      },
      "s3_key": "generated-ads/{generation_id}/candidate-0.png",
      "image_url": "string (S3 presigned URL)",
      "qa_result": {
        "checks": [{"name": "cta_presence", "passed": true, "detail": "string"}],
        "passed": true
      },
      "qa_passed": true,
      "explanation": {
        "applied_target": "string",
        "applied_strategy": "string",
        "applied_template": "string",
        "rationale": "string"
      }
    }
  ],
  "publish_logs": [
    {
      "id": "uuid",
      "candidate_id": "uuid | null",
      "platform": "instagram",
      "status": "published | failed | mocked",
      "ig_media_id": "string | null",
      "caption": "string | null",
      "error_message": "string | null",
      "created_at": "ISO8601"
    }
  ]
}
```

---

### POST /api/generator/generations/{generation_id}/select

Save user's selected candidate.

**Request Body**
```json
{
  "candidate_id": "uuid"
}
```

**Response 200**
```json
{
  "generation_id": "uuid",
  "selected_candidate_id": "uuid"
}
```

---

### POST /api/generator/generations/{generation_id}/publish

Publish selected candidate to Instagram (user approval action). Requires prior `select`. Without `META_ACCESS_TOKEN` / `META_IG_USER_ID`, runs in Mock mode (`status: mocked`).

**Request Body**
```json
{
  "candidate_id": "uuid",
  "caption": "string"
}
```

**Response 200**
```json
{
  "generation_id": "uuid",
  "candidate_id": "uuid",
  "status": "published | failed | mocked",
  "success": true,
  "mocked": true,
  "media_id": "string | null",
  "error": "string | null"
}
```

**Response 400** — candidate not selected first
```json
{"detail": "선택된 후보만 게시할 수 있습니다. 먼저 후보를 선택하세요."}
```

---

### GET /api/generator/generations

List generation history (newest first).

**Query**: `limit` (default 20)

**Response 200**
```json
{
  "generations": [
    {
      "generation_id": "uuid",
      "status": "completed",
      "product_name": "string",
      "selected_candidate_id": "uuid | null",
      "created_at": "ISO8601"
    }
  ]
}
```

---

## 9. Ad Management (4-2)

> Prefix `/api/management` (자동화 결과 조회만 `/api/automation`). JWT 사용자 + org 스코프 인가.
> **원칙**: 지출성 조작은 전부 「제안(ActionProposal) → 승인(ApprovedAction) → 실행(Executor)」 3단계를 거친다.
> 실행 모드 mock / dry_run / validate_only / live — `use_mock=True`면 live 봉인.
> 엔드포인트가 많아 핵심 4개만 상세 스펙, 나머지는 표 요약. 정본은 `backend/api/routers/management.py`.

### 9.1 캠페인 조회·운영

| Method | Path | 설명 |
|---|---|---|
| GET | `/campaigns` | 목록 + 페이징 (mock/실연동 자동 분기, 소프트삭제 reconcile) |
| GET | `/campaigns/{id}` | 상세 (+진단 요약) |
| GET | `/campaigns/{id}/outcome` · `/platforms` · `/demographics` · `/creatives` · `/targeting` · `/leads` | 실측·분해 조회 |
| GET | `/campaigns/{id}/delivery-status` · `/sync` | 게재 상태·Meta 동기화 |
| GET | `/campaigns/{id}/creative-image` | 소재 이미지 프록시 |
| POST | `/campaigns/{id}/activate` · `/pause` | 게재 시작/일시중지 (제안→승인→실행 내부 경유) |
| DELETE | `/campaigns/{id}` | 소프트 삭제 + Meta 동시 삭제 |
| GET | `/campaign-policy` | 최소예산 등 정책 단일원천 (프론트 자동 반영) |
| POST | `/ad-image` · `/ad-preview` | 이미지 업로드(image_hash)·미리보기 |

### 9.2 캠페인 생성·실행 파이프라인

| Method | Path | 설명 |
|---|---|---|
| POST | `/campaigns/create-proposal` | 직접 입력 → CREATE_CAMPAIGN 제안 |
| POST | `/campaign-proposals/from-candidate` | 4-3 시안 → 제안 |
| POST | `/campaign-proposals/from-simulation` | 4-1 시뮬 결과 → 제안 (상세 ↓) |
| POST | `/campaigns/{id}/replace-creative-proposal` | 소재 교체 제안 |
| GET | `/campaign-proposals/name-suggestions` | 캠페인명 제안 |
| POST | `/approve` | 승인 플레인 — 3단계 검증(만료/해시/정책버전) 후 ApprovedAction 발행. 409=검증 실패 `{issues:[…]}` |
| POST | `/execute` | 실행 (상세 ↓) |
| POST | `/regenerate` | 재생성 agent — 진단 → 4-3 위임 생성 → guard → `AWAITING_SELECTION`(후보+selection_token) 또는 `PROPOSED`(제안) |
| GET | `/created-campaigns` | 우리가 생성한 캠페인 레지스트리 |
| GET | `/audit?approval_id=` · `/execution/history` | 감사 로그·실행 이력 |

#### POST /api/management/campaign-proposals/from-simulation

시뮬 결과에서 캠페인 생성 제안. 집행가능 판정(클릭의향률·거부율 게이트)을 통과해야 한다.

**Request**
```json
{
  "simulation_id": "uuid",
  "name": "string",
  "daily_budget_krw": 10000,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD | null (기본 시작+7일)",
  "link_url": "https://… | null",
  "special_ad_category": "NONE | HOUSING | EMPLOYMENT | CREDIT | ISSUES_ELECTIONS_POLITICS",
  "country": "KR", "age_min": 18, "age_max": 65, "gender": "all | male | female"
}
```

**Responses** — 200 `{proposal: ActionProposal}` / 404 시뮬 없음·타 org / 409 집계 미완료 또는 집행 권장 아님 / 422 이미지·link_url·최소예산·날짜 검증 실패 / 502 Meta 이미지 업로드 실패

#### POST /api/management/execute

승인된 액션의 실행 — 모든 지출의 단일 경로. 승인 후 4단계 재검증(유효성·state_version·예산 총액·멱등키) 후 Writer 호출.

**Request**
```json
{"approved_action": "ApprovedAction", "proposal": "ActionProposal"}
```

**Responses** — 200 `{"result": "ActionResult", "error_message?": "Meta 사용자용 안내(실패 시)"}` / 403 타 org 제안·승인. 데모 제안(시연 tenant)은 항상 DRY_RUN. 같은 승인 건 재호출은 멱등키로 1회만 집행.

### 9.3 운영 알림 (이상 감지)

| Method | Path | 설명 |
|---|---|---|
| GET | `/notifications` | org 전체 목록 + `unread_count`. 쿼리: `project_id` `unread_only` `include_resolved` `limit(≤200)` 커서 `before`+`before_id` |
| GET | `/notifications/stream` | 변경 SSE (상세 ↓) |
| POST | `/notifications/read` | bulk 열람 마킹 `{ids:[…]}` → `{updated}` |
| POST | `/notifications/{id}/resolve` | 해소 `{resolution: "ignored"|"actioned"}` |
| POST | `/notifications/{id}/consult` | [상담하기] (상세 ↓) |
| GET | `/anomaly/scan` | 진단 데모(fault 주입) |
| POST | `/anomaly/notify-scan` | 수동 "지금 점검" — 워커 스캐너를 org 스코프로 재사용 |

#### GET /api/management/notifications/stream

org 구독 SSE. 이벤트는 `changed` 신호뿐 — 수신 측이 목록을 refetch한다. EventSource가 아니라 **fetch 스트리밍**(Authorization 헤더)으로 소비.

```
data: {"event": "connected"}      ← 연결 직후 1회
data: {"event": "changed"}        ← 알림 변경 시
: keep-alive                      ← 30초 heartbeat (프록시 타임아웃 방지)
```

404 = `management_notify_sse_enabled=false` (폴링 폴백).

#### POST /api/management/notifications/{id}/consult

알림 → 채팅 상담 전이. 재검증 후 프로젝트 전용 세션에 상담 카드를 심고 이동한다(재클릭은 이동 전용).

**Response 200** — status별 분기
```json
{"status": "consult", "session_id": "uuid"}          // 세션으로 이동
{"status": "normal", "message": "…"}                  // 재검증 결과 정상 → auto_normal 해소
{"status": "already_resolved", "resolution": "…"}     // 이미 해소된 알림
```

404 = 없음·타 org(존재 비노출) / 503 = `unavailable`(상담 준비 실패, 재시도 안내)

### 9.4 예산

| Method | Path | 설명 |
|---|---|---|
| GET | `/budget` · POST `/budget/limit` | 테넌트 예산 현황·한도 설정 |
| POST | `/campaigns/{id}/budget-proposal` → `/budget-commit` | 예산 변경 제안(검증) → 승인 실행 분리 |
| GET | `/budget/rebalance-proposal` | 저효율→고효율 리밸런싱 제안(읽기 전용, 실행은 budget-commit) |
| GET | `/kpi-overrides` · PUT `/campaigns/{id}/kpi-override` | 캠페인별 KPI 목표 덮어쓰기 |

### 9.5 성과 비교·캘리브레이션

`GET /compare` · `/compare/board` · `/compare/before-after`(시뮬 예측 vs 실측) · `GET /calibration/anchors` · `POST /campaigns/{id}/link-simulation`

### 9.6 어시스턴트(CLIO)·KB

`POST /assistant`(에이전틱 RAG 질의) · `POST /kb/refresh` · `POST /kb/eval/generate` · `GET /kb/eval/run` · `GET /kb/eval/faithfulness`

### 9.7 에스컬레이션 사다리

`POST /re-evaluate`(재평가 → 다음 사다리 제안) · `POST /re-evaluate/executed` · `POST /re-evaluate/rejected`

### 9.8 Meta 연동 (org OAuth)

`GET /meta/connect`(인증 URL) → `GET /meta/callback`(state CSRF 검증, 토큰 암호화 저장)

### 9.9 리포트·자동화

| Method | Path | 설명 |
|---|---|---|
| GET | `/report/weekly?period=` | 기간별 성과 리포트(읽기 전용 집계) |
| GET | `/api/automation/runs` | 워커 실행 결과 조회(3도메인 공용). 쿼리: `domain` `project_id` `unresolved` `limit(≤100)` |

---

## 10. A/B Comparison [Target: 7.8]

### POST /api/compare/ab

Compare two ad simulation results.

**Response 501**
```json
{"detail": "A/B comparison is a 7.8 target feature."}
```

---

## 11. Common Error Responses

| HTTP | Code | Description |
|---|---|---|
| 400 | INVALID_INPUT | Input validation error |
| 404 | NOT_FOUND | Resource not found |
| 422 | VALIDATION_ERROR | Pydantic validation error |
| 500 | INTERNAL_ERROR | Internal server error |
| 501 | NOT_IMPLEMENTED | Feature not yet implemented |

```json
{
  "error_code": "string",
  "detail": "string",
  "timestamp": "ISO8601"
}
```
