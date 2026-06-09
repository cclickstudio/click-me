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

| 항목 | 버전 |
|---|---|
| **Python** | 3.12 (`uv`가 자동 설치) |
| **uv** | 최신 |

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

| 변수 | 설명 |
|---|---|
| `DATABASE_URL` | NeonDB PostgreSQL 연결 문자열 |
| `OPENAI_API_KEY` | OpenAI API 키 |
| `ANTHROPIC_API_KEY` | Anthropic API 키 |
| `LANGCHAIN_API_KEY` | LangSmith 트레이싱 키 |
| `AWS_ACCESS_KEY_ID` | AWS IAM 액세스 키 |
| `AWS_SECRET_ACCESS_KEY` | AWS IAM 시크릿 키 |
| `SQS_SIMULATION_QUEUE_URL` | SQS 큐 URL |

### 3. DB 마이그레이션

```bash
uv run alembic upgrade head
```

---

## 실행 방법

### 개발 서버 (핫 리로드)

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

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

## 환경 변수

전체 목록은 [`.env.example`](.env.example) 참고.

---

## 프로젝트 구조

```
backend/
├── api/                         # FastAPI 라우터 레이어
│   ├── main.py                  # 앱 진입점, CORS, 라우터 등록
│   └── routers/
│       ├── chat.py              # 채팅 + SSE 스트리밍
│       ├── simulate.py          # 시뮬레이션 요청 / 결과 조회
│       ├── ads.py               # 광고 업로드 / 분석 / 리포트
│       └── admin.py             # 관리자 전용
│
├── agents/                      # LangGraph 에이전트
│   ├── agent-ad-simulator/      # 시뮬레이션 파이프라인
│   ├── agent-ad-creator/        # 광고 생성 [7.8]
│   └── agent-ad-management/     # 플랫폼 게시/내리기
│
├── tools/                       # @tool 재사용 함수
│   ├── ad_analysis/vision.py    # GPT-4o Vision 분석
│   ├── persona/factory.py       # OCEAN 페르소나 생성
│   ├── simulation/              # exposure / deliberation / ssr_scorer
│   ├── storage/                 # S3, SQS
│   └── search/rag.py            # pgvector RAG 검색
│
├── core/
│   ├── config.py                # pydantic-settings 환경변수
│   ├── db.py                    # AsyncSession, get_db
│   └── models.py                # SQLAlchemy ORM 모델
│
├── pyproject.toml
├── .python-version              # Python 3.12 고정
└── .env.example
```
