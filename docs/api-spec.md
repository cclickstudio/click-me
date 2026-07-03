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

## 9. A/B Comparison [Target: 7.8]

### POST /api/compare/ab

Compare two ad simulation results.

**Response 501**
```json
{"detail": "A/B comparison is a 7.8 target feature."}
```

---

## 10. Common Error Responses

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
