# ClickMe Backend

FastAPI + LangGraph 기반 AI 광고 시뮬레이션 플랫폼 백엔드.

---

## 목차

- [요구 사항](#요구-사항)
- [개발 환경 세팅](#개발-환경-세팅)
- [실행 방법](#실행-방법)
- [환경 변수](#환경-변수)
- [프로젝트 구조](#프로젝트-구조)

---

## 요구 사항

| 항목       | 버전                    |
| ---------- | ----------------------- |
| **Python** | 3.12 (`uv`가 자동 설치) |
| **uv**     | 최신                    |

### uv 설치

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

---

## 개발 환경 세팅

### 1. 의존성 설치

```bash
cd backend
uv sync
```

`uv sync`가 한 번에 처리합니다:

- `.python-version` 기반 Python 3.12 자동 설치
- 가상환경(`.venv`) 생성 + 패키지 설치

### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일에 아래 항목을 채웁니다:

| 변수                       | 설명                          |
| -------------------------- | ----------------------------- |
| `DATABASE_URL`             | NeonDB PostgreSQL 연결 문자열 |
| `OPENAI_API_KEY`           | OpenAI API 키                 |
| `ANTHROPIC_API_KEY`        | Anthropic API 키              |
| `LANGSMITH_API_KEY`        | LangSmith 트레이싱 키         |
| `AWS_ACCESS_KEY_ID`        | AWS IAM 액세스 키             |
| `AWS_SECRET_ACCESS_KEY`    | AWS IAM 시크릿 키             |
| `AUTH_PROVIDER`            | `local`(기본, 자체 HS256) \| `cognito`(운영) |
| `COGNITO_USER_POOL_ID`     | `AUTH_PROVIDER=cognito`일 때 필수 |
| `COGNITO_APP_CLIENT_ID`    | Cognito App Client ID(토큰 검증) |

### 3. DB 마이그레이션

```bash
uv run alembic upgrade head
```

---

## 실행 방법

### 개발 서버 (핫 리로드)

```bash
uv run dev.py
```

> `dev.py`는 `.venv` 디렉터리를 감시 대상에서 제외하고 `api`, `agents`, `tools`, `core` 디렉터리만 watch합니다.  
> Windows에서 `uv run uvicorn ... --reload` 실행 시 `.venv` 내부 파일 변경 이벤트로 인해 서버가 무한 재시작되는 문제를 방지합니다.

### 프로덕션 서버

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 헬스 체크

```bash
curl http://localhost:8000/health
# {"status":"ok","env":"development"}
```

API 문서: `http://localhost:8000/docs`

---

## 코드 품질

```bash
uv run ruff check .          # 린트 검사
uv run ruff check . --fix    # 자동 수정
uv run ruff format .         # 포맷 적용
uv run pytest                # 테스트 실행
```

---

## 문서 자동 생성 (API 엔드포인트 · 프론트 라우트)

라우터(`api/`)나 프론트 페이지(`frontend/src/app/`)를 추가하면 아래 문서가 코드에서 자동 생성된다 — **직접 편집 금지**.

- `docs/api-endpoints.md` — FastAPI 앱(`api.main:app`)의 전체 엔드포인트
- `docs/frontend-routes.md` — Next.js App Router 전체 라우트
- `CLAUDE.md`의 AUTOGEN 구간 — 위 두 문서 개수·링크

```bash
uv run python scripts/gen_docs.py          # 재생성
uv run python scripts/gen_docs.py --check  # 동기화 검사(CI에서 사용, 어긋나면 실패)
```

커밋 시 자동 갱신하려면 훅을 1회 설치한다(저장소 루트에서):

```bash
git config core.hooksPath .githooks
```

미설치·실패해도 CI(`ci-cd.yml`의 *Docs drift check*)가 어긋남을 잡는다.

---

## 환경 변수

전체 목록은 [`.env.example`](.env.example) 참고.

---

## 프로젝트 구조

> DDD + 헥사고날(포트·어댑터) 구조. 핵심 기능을 `domain/` 아래 바운디드 컨텍스트로 분리하고, 도메인 간 공유는 `core`/`tools`/각 도메인 `contracts`로만 한다. 자세한 규칙은 루트 [`CLAUDE.md`](../CLAUDE.md) 참고.

```
backend/
├── api/                         # 전송 계층(FastAPI)
│   ├── main.py                  # 앱 진입점, lifespan, CORS, 라우터 등록(/api/* prefix)
│   ├── routers/                 # 도메인별 라우터 — admin·ads·auth·billing·chat·company·
│   │                            #   dashboard·debate·generator·inquiries·management·
│   │                            #   personas·projects·simulate·simulation/
│   └── assistant/               # 채팅(4-4) 오케스트레이터(통합 딥에이전트, deep_agent_builder)
│
├── domain/                      # 바운디드 컨텍스트(도메인)
│   ├── simulation/              # 4-1 광고 시뮬레이터
│   ├── management/              # 4-2 광고 매니지먼트
│   ├── generator/               # 4-3 광고 생성
│   ├── chat/                    # 4-4 채팅 어시스턴트
│   └── billing/                 # 결제·크레딧
│     └─ (도메인 내부) contracts/ · adapters/ · service/ · graph|agents/ · wiring.py
│
├── tools/                       # 공용 @tool — ad_analysis · persona · simulation · storage · search
│
├── core/                        # 공통 인프라
│   ├── config.py                # pydantic-settings 환경변수
│   ├── db.py                    # AsyncSession, get_db (Neon)
│   ├── auth.py                  # 인증(local HS256 / Cognito RS256·JWKS)
│   ├── cognito_admin.py         # Cognito 계정 create/disable/enable/delete
│   └── models.py                # SQLAlchemy ORM 모델
│
├── alembic/                     # 마이그레이션(0001_baseline → 0002 → 0003 → 0004)
├── dev.py                       # 개발 서버 진입(.venv watch 제외)
├── pyproject.toml
├── .python-version              # Python 3.12 고정
└── .env.example
```
