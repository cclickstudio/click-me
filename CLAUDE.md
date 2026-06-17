# ClickMe — CLAUDE.md

> 집행 전 AI 가상 소비자에게 광고를 테스트하고, 집행 후 성과를 추적·관리하는 **광고 전주기 지원 플랫폼** (기획서 v1.3).
> 목표는 "실제 사람과 동일한 응답"이 아니라 "직감·내부 검토보다 나은 의사결정 근거" 제공.

## Key Decisions

- **Backend** FastAPI (Python only, No Spring) / **PM** uv(backend)·pnpm(frontend) 교차 금지 / **Arch** 모놀리식 + 부분 DDD/SOLID, 단일 EC2.
- **MQ** AWS SQS (No Redis — 트래킹 큐 Redis는 탐색 대상, Open Issues 참고).
- **Sim engine** Deepsona(OCEAN) + SSR(arXiv 2510.08338). **Scoring** SSR(임베딩 기반, no LLM, not DLR). **Output** 스칼라 아닌 분포.
- **구매의도 검증** KOBACO 베이스라인 대비. 그 외 신호는 탐색적(exploratory) 표기.
- **인증(타깃)** JWT + 관리자 직접 계정 생성(자가가입·소셜 없음), Admin/User 역할. **(현재)** UI만, 실 JWT 미적용·점진 도입.
- **A/B** UI 선반영, YouTube RAG 실기능은 최종 단계. **Chat** Gemini 2.0 Flash, persona CLIO, SSE — **후순위**.
- **Ad gen** 개선 시안 5개 자동생성+순위 (Gemini Flash 3.0 / GPT Image 2 / Gemini Omni). **PDF** 전체 생성 포함. **문의** in-app 폼 → DB.

## 핵심 기능 (기획서 v1.3)

| #   | 기능              | 설명                                          | 우선순위 |
| --- | ----------------- | --------------------------------------------- | -------- |
| 4-1 | 광고 시뮬레이터   | 집행 전 반응 예측 → 개선 방향·보고서          | 핵심(2인) |
| 4-2 | 광고 매니지먼트   | 목표·예산·플랫폼·성과를 단일 창구 관리        | 핵심(2인) |
| 4-3 | 광고 생성         | 예측 반영 → 개선 시안 5개 생성·기대성과 순위  | 핵심(2인) |
| 4-4 | 채팅 AI 어시스턴트 | 자유질문 + 시뮬·분석·생성 결과 전달          | 후순위    |

> 핵심 3기능 병렬 진행, 채팅(4-4)·팀 관리는 그 완료 후 착수.

**시뮬레이터 4대 KPI** — ① **클릭 의향률**: AISAS Action 통과 비율, 신뢰구간으로 표기 / **"예측 CTR" 등 실측 스케일 환산 금지**(실측 누적 후 calibration 해금). ② **구매의도**: 1~5점 평균+분포(분포 전체 표시, 평균 단언 금지). ③ **신뢰도**: 1~5점 평균. ④ **거부율**: 거부 비율 + 사유 분해.

## 로드맵 / 비즈니스

- **로드맵** 베이스라인 2026-06-12 ✅ → 최종 구현 2026-07-08(핵심 3기능 + 채팅·팀관리) → 발표 2026-07-14.
- **플랜(UI만, 실과금 추후)** Free(개인·제한 시뮬·트래킹 1개) / Professional(팀·확장·무제한 트래킹·API 연동) / Enterprise(기업·대규모·다채널).
- **조직** = 결제 단위(플랜 공유), **프로젝트** = 캠페인 단위(시안+매니지먼트), **팀 관리** = 프로젝트 협업(뷰어/에디터/오너).

## 인증 및 보안

- 소셜 로그인·자가가입 없음, **관리자가 직접 계정 생성**. JWT 기반, Admin/User 역할.
- 기밀 데이터(예산·크리에이티브) 평문 로그 금지. 외부 플랫폼 API 키는 암호화 저장(AES-256 또는 AWS Secrets Manager).
- 현재 페이즈: admin API는 `/api/admin/*` 경로 프리픽스로만 제한.

## Tech Stack

- **Frontend** Next.js(TS) + Tailwind (pnpm) / **Backend+AI** FastAPI + LangGraph (uv).
- **DB** NeonDB(PostgreSQL + pgvector, vector(1536)) / **MQ** AWS SQS / **Storage** AWS S3.
- **Deploy** 단일 EC2 + Nginx / **CI/CD** GitHub Actions(Docker) / **Tracing** LangSmith / **Chat LLM** Gemini 2.0 Flash(`google-generativeai>=0.8.0`).

## 백엔드 아키텍처 (DDD)

핵심 3기능을 각각 `backend/domain/` 아래 **바운디드 컨텍스트**로 분리한 DDD + 헥사고날(포트·어댑터) 구조. 도메인 간 직접 의존 금지, 공유는 `core`/`tools`/각 도메인 `contracts`로만.

```
backend/
├── core/      공통 인프라: config.py(settings) · db.py(async/Neon) · models.py(ORM) · schemas.py
├── api/       전송 계층: main.py(앱·라우터등록·lifespan·CORS) · routers/(도메인별, /api/* prefix)
├── tools/     공용 도구: simulation(ssr_scorer·exposure·deliberation·anchors) · persona · ad_analysis · storage · search
└── domain/    바운디드 컨텍스트(팀당 1개): generator(4-3) · management(4-2) · simulation(4-1)
```

**도메인 내부 레이어** — `contracts/`(포트·스키마·enum, 외부 의존 없음) · `adapters/`(포트 구현체·외부연동·mock) · `service/`(유스케이스·DB영속·SSE) · `graph/`·`agents/`(LangGraph) · `wiring.py`(Composition Root, mock↔실연동 전환 유일 지점). management는 추가로 `detection/`·`execution/`·`evals/`.

**의존성** `api/routers → domain/<ctx>/service → contracts(포트) ← adapters(구현)`. DB·설정은 `core`, LLM·SDK 래퍼는 `tools`에서만. mock/실연동 교체는 `wiring.py`에서만.

> 이전 현황: generator·management는 `domain/` 이전 완료. simulation은 `tools/simulation/`·평면 라우터 → `domain/simulation/`·`api/routers/simulation/`로 이전 진행 중.

## 협업 규칙 (충돌 방지)

원칙: **"자기 도메인은 자유롭게 / 공통부는 조율 후"**. 통합 충돌은 대부분 공통부 동시 수정에서 발생.

- **소유권** `domain/{simulation|management|generator}/`, 자기 `api/routers/*`, 자기 팀이 쓰는 `tools/*` 하위는 해당 팀만 수정·타 팀은 읽기만.
- **공통부**(`core/`·`api/main.py`·공용 `tools/`·`docs/`·`CLAUDE.md`·`docker-compose`·CI) 변경 시
  1. 작은 단독 PR로 분리(도메인 작업과 안 섞기).
  2. **DB 모델·스키마(`core/models.py`·`docs/db-schema.md`) 단독 변경 금지** — 사전 공지 + Alembic.
  3. **`api/main.py` 라우터 등록은 append-only** — 자기 `include_router` 한 줄만, 순서 유지.
  4. 공용 `tools/` 시그니처 변경은 호출 팀 합의 후.
- **경계** 타 도메인 내부 직접 import 금지 → `contracts/` 스키마로만 교환. 공유 로직은 `core`/`tools`로.
- **브랜치** `feat/<domain>-<설명>`, `dev` 자주 rebase, 주간 통합 테스트.

## Environment Variables

```bash
# backend/.env
APP_ENV=development
OPENAI_API_KEY= / ANTHROPIC_API_KEY= / GEMINI_API_KEY=   # 채팅(Gemini 2.0 Flash)
DATABASE_URL=postgresql+asyncpg://user:pw@host/db?sslmode=require
AWS_ACCESS_KEY_ID= / AWS_SECRET_ACCESS_KEY= / AWS_REGION=ap-northeast-2
S3_BUCKET_NAME= / SQS_SIMULATION_QUEUE_URL=
LANGSMITH_TRACING_V2=true / LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_API_KEY= / LANGSMITH_PROJECT=clickme-v2
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## CI/CD 현황

- **CI** (`ci.yml`) ✅ — `backend`(ruff + pytest), `frontend`(ESLint + build) 활성 / `docker-build` ⏸(Secrets 후 활성).
- **CD** (`cd.yml`) ⏳ — 틀만 작성. 활성화 조건: Docker Hub·EC2·기타 Secrets 등록 + `on.push` 및 각 step 주석 해제. EC2/Docker Hub 준비 후 진행.

## 개발 워크플로우 (Claude 행동 규칙)

**커밋 컨벤션** `타입: 한국어 설명` — `add`(새 기능/파일) · `delete`(삭제) · `edit`(수정/리팩토링) · `fix`(버그). 예: `add: 시뮬레이션 기능 추가`.

**① 백엔드 .py 수정 직후 (IMPORTANT)** — 커밋 메시지 출력 **전에** Ruff 실행을 제안한다: *"백엔드 코드가 변경됐어요. 커밋 전에 Ruff로 맞춰두면 CI에서 안 막혀요. Ruff 실행할까요?"*
- 수락(응/해줘/yes/ㅇㅇ) → `cd backend && uv run ruff format . && uv run ruff check . --fix` 실행.
- 거절(나중에/ㄴㄴ) → 바로 커밋 메시지로. **프론트(TS)만 수정 시 생략.**
- 왜: CI(`ci.yml`)가 `ruff check`로 검증. 로컬 선통과 안 하면 push 후 CI 실패. (pytest는 느리고 비용↑이라 별개.)

**② 구현 완료 시** — `타입: 설명` + 변경 불릿 형태의 커밋 메시지와 `git add . && git commit -m "…"`를 출력. 사소한 작업도 출력, 여러 기능은 기능별로 분리 제안.

**③ GitHub Issue 요청 시** — 먼저 `gh --version`으로 설치 확인. 미설치면 OS별 설치 안내(winget `GitHub.cli` / brew `gh` / apt `gh` → `gh auth login`) 후 `gh issue create` 제공. label은 `enhancement`/`bug`/`refactor`/`chore` 중 선택.

**④ Issue 일괄 생성 스크립트** — 반드시 **Python(`.py`)** 으로 제공(`.ps1`/`.sh` 금지). 백엔드에 포함된 `httpx`로 GitHub REST API(`POST /repos/{repo}/issues`, `Bearer` 토큰) 호출, `uv run python create_issues.py` 실행.

## AI 작업 규칙 (행동 가이드라인)

1. **코딩 전 생각** — 가정 명시·불확실하면 질문. 해석이 여럿이면 제시(침묵 선택 금지). 더 단순한 길 있으면 제안.
2. **단순성 우선** — 요청 범위 밖 기능·추상화 금지. 200줄을 50줄로 줄일 수 있으면 다시 쓴다.
3. **수술적 변경** — 고칠 곳만. 인접 코드·포맷 임의 "개선" 금지, 기존 스타일 유지. 무관한 죽은 코드는 언급만.
4. **목표 기반** — 검증 가능한 성공 기준으로 변환("검증 추가"→"실패 테스트 작성 후 통과"). 다단계는 계획 먼저.
5. **한국어 출력, 끝에 콜론 금지** — 사용자가 한국어면 출력도 한국어. 문장은 `.`/`?`/`!`로 종료(`:`는 코드·키:값·라벨 내부만).
6. **새 파일 첫 줄 한국어 헤더 주석** — 역할 한 줄(지시문/shebang 바로 아래). 설정 파일 제외. 예: `# KIS API를 비동기로 래핑하는 클라이언트`.
7. **계획+체크리스트+컨텍스트 노트** — 비자명한 작업 전 `checklist.md`·`context-notes.md` 작성. 계획만 받으면 멈추고 노트부터 만들지 확인.
8. **완료 전 테스트** — 코드 건드렸으면 `pytest`/`pnpm` 실행, 실패 시 고치고 재실행. 셋업 없으면 최소 빌드 확인. "끝"이라 하기 전에 선제적으로.
9. **시맨틱 커밋** — 한 논리 단위 = 한 커밋("한 문장 설명 가능?"). 무관한 변경 쌓지 않기.
10. **에러는 읽어라** — 전체 에러·스택·실로그 확인 후 수정. 원인 확인 전 "흔한 수정" 적용 금지.

## Open Issues

| 항목                                | 비고                                                            |
| ----------------------------------- | --------------------------------------------------------------- |
| 트래킹 큐 Redis 도입 여부           | 결정은 No Redis(SQS). 기획서 리스크표가 Redis 큐 언급 → 보류·탐색. |
| 인증 실구현 (JWT 자체 vs Cognito)   | 타깃 JWT + 관리자 계정 생성. 토큰 발급/검증 도입 시점·방식 미정.  |
| 채팅(4-4) 착수 시점                 | 핵심 3기능 완료 후. 현재 `/chat`은 선반영.                       |
| CD 활성화                           | Docker Hub + EC2 Secrets 등록 필요.                             |

## Reference

- API 엔드포인트 → `docs/api-spec.md` / DB 스키마·Alembic → `docs/db-schema.md`.
- **PM 규칙** pnpm은 `backend/` 금지, uv는 `frontend/` 금지.
- **Dev** 백엔드 `cd backend && uv run uvicorn api.main:app --reload --port 8000` / 프론트 `cd frontend && pnpm dev` / 전체 `docker compose up --build` / 테스트 `cd backend && uv run pytest tests/ -v`.
