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
| Chat advisor | Gemini 2.0 Flash. Persona: CLIO (광고 전략 AI 어드바이저). SSE streaming. |
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
| Chat LLM | Google Gemini 2.0 Flash | `google-generativeai>=0.8.0` |

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
GEMINI_API_KEY=          # 채팅 어드바이저 (Gemini 2.0 Flash)
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

## CI/CD 현황

### CI — `.github/workflows/ci.yml` ✅ 완료
| 잡 | 내용 | 상태 |
|---|---|---|
| `backend` | ruff lint/format + pytest | ✅ 활성 |
| `frontend` | ESLint + Next.js build | ✅ 활성 |
| `docker-build` | Docker 이미지 빌드 검증 | ⏸ 주석 처리 (Secrets 등록 후 활성화) |

### CD — `.github/workflows/cd.yml` ⏳ 미완성
전체 파이프라인 틀은 작성됐으나, **아래 작업 완료 후 주석 해제 필요**:

1. **Docker Hub Secrets 등록** (`DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`)
2. **EC2 Secrets 등록** (`EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`)
3. **기타 Secrets 등록** (`NEXT_PUBLIC_API_URL`, `SLACK_WEBHOOK_URL`)
4. `cd.yml`의 `on.push` 트리거 주석 해제 + 각 step 주석 해제

> EC2 서버 세팅 및 Docker Hub 계정 준비가 되면 진행할 것.

---

## Open Issues

| Item | Scope |
|---|---|
| Finalize segment enum list | P2 segment breakdown output |
| Auth method for 7.8 (JWT vs Cognito) | DB `refresh_tokens`, API auth headers |
| Define share_intent KPI | P2 output |
| Remove `simulation_type = 'survey'` | DB enum migration |
| Select sample ads for demo | KOBACO comparison demo |
| CD 파이프라인 활성화 (Docker Hub + EC2 Secrets 등록) | 배포 자동화 |

---

## Reference Docs

| Task | Doc |
|---|---|
| API endpoints | `docs/api-spec.md` |
| DB schema / Alembic migration | `docs/db-schema.md` |

---

## 개발 워크플로우 (Claude 행동 규칙)

### 커밋 메시지 컨벤션

| 타입 | 사용 상황 |
|---|---|
| `add` | 새 기능, 새 파일 추가 |
| `delete` | 파일 또는 기능 삭제 |
| `edit` | 기존 기능 수정, 리팩토링 |
| `fix` | 버그 수정, 오류 해결 |

형식: `타입: 한국어 설명`
예시: `add: 시뮬레이션 기능 추가`

---

### Claude 자동 출력 규칙 (IMPORTANT — 반드시 따를 것)

#### 백엔드 코드 수정 후 → Ruff 실행 제안 (IMPORTANT)

백엔드 Python 파일을 수정한 직후, **커밋 메시지를 출력하기 전에** 반드시 아래 멘트로 Ruff 실행을 제안한다.

> "백엔드 코드가 변경됐어요. 커밋 전에 Ruff로 린트·포맷을 맞춰두면 CI에서 막히지 않아요.  
> **Ruff 실행할까요?** (몇 초면 끝나고, import 순서·스타일 오류를 자동으로 고쳐줘요)"

- 팀원이 **"응 / 해줘 / yes / ㅇㅇ"** 등으로 수락하면 → 즉시 아래 명령어를 실행한다:

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
```

- 팀원이 **"괜찮아 / 나중에 / no / ㄴㄴ"** 등으로 거절하면 → 실행하지 않고 커밋 메시지 출력으로 넘어간다.
- **프론트엔드(TypeScript) 파일만 수정한 경우**에는 이 제안을 생략한다.

> **왜 중요한가**: Ruff는 수초면 끝나며 API 비용도 없다. CI(`ci.yml`)가 `ruff check`로 백엔드를 검증하므로, 로컬에서 미리 통과시켜 두지 않으면 push 후 CI가 실패한다. `pytest`(10분+, API 비용)와 달리 Ruff는 커밋마다 돌려도 부담이 없다.

---

#### 기능 구현 완료 시점 → 커밋 메시지 출력

구현이 완료됐다고 판단되는 시점(코드 수정 완료, 정상 동작 확인 후)에 아래 형식으로 커밋 메시지를 출력한다.

```
타입: 한국어 설명

- 변경 사항 1
- 변경 사항 2
```

전체 커밋 명령어도 함께 출력:
```bash
git add .
git commit -m "타입: 한국어 설명"
```

- 단순 오류 수정이나 스타일 변경 등 사소한 작업도 커밋 메시지를 출력한다
- 여러 기능을 한 번에 구현한 경우 기능별로 커밋을 분리해서 제안

#### GitHub Issue (`gh`) 요청 시 → 설치 여부 먼저 확인

팀원이 GitHub Issue 생성 코드를 요청하면, `gh` CLI 설치 여부를 **먼저 확인**한다.

```bash
gh --version
```

- **설치되어 있으면** → 바로 `gh issue create` 명령어를 제공한다
- **설치되어 있지 않으면** → 아래 순서로 설치 방법을 단계별로 안내한 뒤 명령어를 제공한다

**Windows (winget)**
```bash
winget install --id GitHub.cli
# 설치 후 터미널 재시작
gh auth login   # GitHub 계정 인증 (브라우저 열림)
gh --version    # 설치 확인
```

**macOS (Homebrew)**
```bash
brew install gh
gh auth login
gh --version
```

**Linux (apt)**
```bash
sudo apt install gh
gh auth login
gh --version
```

인증 완료 후 `gh issue create` 명령어를 제공한다.
label은 상황에 따라 `enhancement` / `bug` / `refactor` / `chore` 중 선택한다.

#### Issue 생성 스크립트 포맷 → 반드시 Python 스크립트로 제공

팀원이 Issue를 **스크립트로 일괄 생성**하는 코드를 요청할 경우, 파일 포맷은 **반드시 Python(`.py`)으로** 제공한다. PowerShell(`.ps1`) 또는 셸 스크립트(`.sh`)로 제공하지 않는다.

Python 스크립트 기본 구조 (GitHub REST API 사용):

```python
import httpx

GITHUB_TOKEN = "ghp_your_token_here"
REPO = "org/repo-name"  # 실제 레포로 교체

headers = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

issues = [
    {"title": "이슈 제목 1", "body": "설명", "labels": ["enhancement"]},
    {"title": "이슈 제목 2", "body": "설명", "labels": ["bug"]},
]

with httpx.Client() as client:
    for issue in issues:
        res = client.post(
            f"https://api.github.com/repos/{REPO}/issues",
            headers=headers,
            json=issue,
        )
        print(f"[{res.status_code}] {issue['title']}")
```

`httpx`는 이미 백엔드 의존성에 포함되어 있으므로 `uv run python create_issues.py`로 바로 실행 가능하다.
