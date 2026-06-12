# ClickMe API Specification

| Version | v2.0 |
|---|---|
| Date | 2026-06-09 |
| Base URL | `http://localhost:8000/api` (dev) |
| Content-Type | `application/json` |

---

## 1. Authentication

### Phase 1 (6.12)
No auth. Role selection is local client state only.
Admin APIs are restricted by path prefix `/api/admin/*`.

### Phase 2 (7.8, TBD)
- `Authorization: Bearer <access_token>` header to be added
- JWT self-implementation or AWS Cognito under review

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

Start async simulation task. Publishes to SQS and returns immediately.

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

> Phase 1: restricted by path prefix `/admin/*`.

### GET /api/admin/users

List users.

**Response 200**
```json
{
  "users": [
    {
      "user_id": "uuid",
      "email": "string",
      "name": "string",
      "role": "admin | user",
      "created_at": "ISO8601",
      "last_login_at": "ISO8601 | null"
    }
  ]
}
```

---

### POST /api/admin/users

Create a user account.

**Request Body**
```json
{
  "email": "string",
  "name": "string",
  "role": "admin | user",
  "initial_password": "string"
}
```

**Response 201**
```json
{"user_id": "uuid"}
```

---

### GET /api/admin/inquiries

List customer inquiries.

**Response 200**
```json
{
  "inquiries": [
    {
      "inquiry_id": "string",
      "title": "string",
      "content": "string",
      "contact_email": "string | null",
      "created_at": "ISO8601"
    }
  ]
}
```

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
