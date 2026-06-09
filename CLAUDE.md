# ClickMe — CLAUDE.md

> AI-powered ad performance prediction platform. Test ads against AI-generated virtual consumers before launch.

---

## Key Decisions

| Item | Decision |
|---|---|
| Backend | FastAPI (Python only). No Java Spring Boot. |
| Package managers | uv (backend), pnpm (frontend). Cross-use forbidden. |
| Architecture | Monolith + partial DDD + SOLID. Single EC2. |
| Message queue | AWS SQS. No Redis. |
| Simulation engine | Deepsona (OCEAN) + SSR paper (arXiv 2510.08338). |
| Scoring | SSR (embedding-based, no LLM). Not DLR (direct number output). |
| Output format | Distribution. Not a scalar score. |
| Purchase intent validation | Compare against KOBACO baseline. Other signals are exploratory. |
| Auth 6.12 | UI only (role selection button). No real JWT. |
| Auth 7.8 | TBD (JWT self-impl vs Cognito). |
| A/B comparison | UI in 6.12, YouTube RAG actual feature in 7.8. |
| Ad generation | Gemini Flash 3.0 / GPT Image 2 / Gemini Omni. [7.8] |
| PDF report | Full generation included in 6.12. |
| Customer inquiry | In-app form → DB storage. |

---

## Tech Stack

| Area | Tech | Notes |
|---|---|---|
| Frontend | Next.js (TypeScript) + Tailwind CSS | pnpm |
| Backend + AI | Python FastAPI + LangGraph | uv |
| DB | NeonDB (PostgreSQL + pgvector) | vector(1536) |
| Message queue | AWS SQS | Async simulation processing |
| Storage | AWS S3 | Ad files, generated images |
| Deploy | Single EC2 instance | Nginx reverse proxy |
| CI/CD | GitHub Actions | Docker containers |
| Tracing | LangSmith | AI pipeline tracing |

---

## Directory Structure

```
click-me/                        ← monorepo root
├── docker-compose.yaml
├── .gitignore
├── CLAUDE.md
├── docs/
│   ├── api-spec.md              ← API endpoint reference
│   └── db-schema.md             ← Full SQL schema + Alembic migration
│
├── frontend/                    ← Next.js (pnpm owns this)
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── src/
│       ├── app/                 ← App Router (route = directory/page.tsx)
│       │   ├── page.tsx         → /
│       │   ├── sign-in/page.tsx → /sign-in
│       │   ├── sign-up/page.tsx → /sign-up
│       │   ├── chat/page.tsx    → /chat
│       │   ├── simulation/page.tsx → /simulation
│       │   ├── generator/page.tsx  → /generator
│       │   ├── manage/page.tsx     → /manage
│       │   └── admin/
│       │       ├── layout.tsx      ← shared admin sidebar
│       │       ├── page.tsx        ← redirects to /admin/dashboard
│       │       ├── dashboard/page.tsx   → /admin/dashboard
│       │       ├── manage-user/page.tsx → /admin/manage-user
│       │       ├── chat-log/page.tsx    → /admin/chat-log
│       │       ├── inquiry/page.tsx     → /admin/inquiry
│       │       └── check/page.tsx       → /admin/check
│       └── components/
│           ├── Navigation.tsx   ← top nav bar (user-facing)
│           ├── AppLayout.tsx    ← Navigation + main wrapper
│           └── AdminSidebar.tsx ← dark sidebar, usePathname active state
│
└── backend/                     ← FastAPI (uv owns this)
    ├── pyproject.toml
    ├── uv.lock
    ├── api/
    │   ├── main.py
    │   └── routers/
    │       ├── chat.py
    │       ├── simulate.py
    │       ├── ads.py
    │       └── admin.py
    ├── agents/
    │   ├── agent-ad-simulator/  ← state.py / nodes.py / graph.py
    │   ├── agent-ad-creator/    ← [7.8]
    │   └── agent-ad-management/
    ├── tools/
    │   ├── ad_analysis/vision.py
    │   ├── persona/factory.py
    │   ├── simulation/          ← exposure.py / deliberation.py / ssr_scorer.py
    │   ├── storage/             ← s3.py / sqs.py
    │   └── search/rag.py
    └── core/
        ├── config.py
        ├── db.py
        └── models.py
```

**Package manager rule**: pnpm forbidden inside `backend/`. uv forbidden inside `frontend/`.

---

## Simulation Pipeline

```
Persona Factory → Exposure → Deliberation → SSR Scoring → [Debate 7.8] → Aggregation → [Improvement P2]
```

| Stage | File | LLM | Temperature |
|---|---|---|---|
| Ad Understanding | `tools/ad_analysis/vision.py` | GPT-4o Vision | 0.1 |
| Persona Factory | `tools/persona/factory.py` | GPT-4o-mini | 0.7 |
| Exposure | `tools/simulation/exposure.py` | GPT-4o-mini | 0.8 |
| Deliberation | `tools/simulation/deliberation.py` | GPT-4o-mini | 0.7 |
| SSR Scoring | `tools/simulation/ssr_scorer.py` | **none** (embedding only) | — |
| Debate [7.8] | `agents/agent-ad-creator/nodes.py` | Claude Haiku | 0.9 |
| Aggregation | in `agents/agent-ad-simulator/nodes.py` | **none** | — |

**SSR key point**: DLR (asking LLM for a number directly) causes center-bias (KS 0.26~0.39). SSR embeds free text → cosine similarity against anchors → distribution (KS 0.80~0.88). See `docs/` for full schema.

---

## Output Priorities

| Priority | Item | Target |
|---|---|---|
| **P0** | Purchase intent distribution (KOBACO-comparable) | 6.12 |
| **P0** | Per-persona free text reaction | 6.12 |
| P1 | Other signal distributions (attention etc.) — **must label as "exploratory"** | 6.12 |
| P1 | KPI (CTR/CVR proxy), Funnel, LangSmith trace | 6.12 |
| **P2** | Segment breakdown, share_intent, improvement suggestions | TBD |

---

## Frontend Routes

### User

| Path | Screen | Phase |
|---|---|---|
| `/` | Landing page | 6.12 |
| `/sign-in` | Sign in | 6.12 |
| `/sign-up` | Sign up | 6.12 |
| `/chat` | AI chat | 6.12 |
| `/simulation` | Ad simulator | 6.12 |
| `/generator` | Ad generator (UI skeleton) | 6.12 UI, 7.8 real |
| `/manage` | Ad management | 6.12 |
| `/compare` | A/B comparison (UI only) | 6.12 UI, 7.8 real |

### Admin

| Path | Screen | Phase |
|---|---|---|
| `/admin` | Redirects to `/admin/dashboard` | 6.12 |
| `/admin/dashboard` | Admin dashboard | 6.12 |
| `/admin/manage-user` | User management | 6.12 |
| `/admin/chat-log` | Chat history | 6.12 |
| `/admin/inquiry` | Customer inquiries | 6.12 |
| `/admin/check` | Usage stats | 6.12 |

---

## Environment Variables

```bash
# backend/.env
APP_ENV=development
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql+asyncpg://user:password@host/dbname?sslmode=require
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=
SQS_SIMULATION_QUEUE_URL=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY=
LANGCHAIN_PROJECT=clickme-v2

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Dev Commands

```bash
# Backend
cd backend && uv run uvicorn api.main:app --reload --port 8000

# Frontend
cd frontend && pnpm dev

# Full stack (Docker)
docker compose up --build

# Backend tests
cd backend
uv run pytest tests/ -v
```

---

## Auth Status

| Phase | Status | Detail |
|---|---|---|
| Phase 1 (6.12) | In progress | Role selection button → local state. No API auth. |
| Phase 2 (7.8) | TBD | JWT self-impl or AWS Cognito |

Phase 1: admin APIs restricted by `/api/admin/*` path prefix only.

---

## Open Issues

| Item | Scope |
|---|---|
| Finalize segment enum list | P2 segment breakdown output |
| Auth method for 7.8 (JWT vs Cognito) | DB `refresh_tokens`, API auth headers |
| Define share_intent KPI | P2 output |
| Remove `simulation_type = 'survey'` | DB enum migration |
| Select sample ads for demo | KOBACO comparison demo |

---

## Reference Docs

| Task | Doc |
|---|---|
| API endpoints | `docs/api-spec.md` |
| DB schema / Alembic migration | `docs/db-schema.md` |
