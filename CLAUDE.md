# ClickMe — CLAUDE.md

> 집행 전 AI 가상 소비자에게 광고를 테스트하고, 집행 후 성과를 추적·관리하는 **광고 전주기 지원 플랫폼** (기획서 v1.3).
> 목표는 "실제 사람과 동일한 응답"이 아니라 "직감·내부 검토보다 나은 의사결정 근거" 제공.

## Key Decisions

- **Backend** FastAPI (Python only, No Spring) / **PM** uv(backend)·pnpm(frontend) 교차 금지 / **Arch** 모놀리식 + 부분 DDD/SOLID, 단일 EC2.
- **비동기 잡** 인프로세스 async(`asyncio.create_task`). 별도 MQ 미사용 — SQS·Redis 모두 안 씀.
- **Sim engine** Deepsona(OCEAN) + SSR(arXiv 2510.08338). **Scoring** SSR(임베딩 기반, no LLM, not DLR). **Output** 스칼라 아닌 분포.
- **구매의도 검증** KOBACO 베이스라인 대비. 그 외 신호는 탐색적(exploratory) 표기.
- **인증** 관리자 직접 계정 생성(자가가입·소셜 없음), 역할 ADMIN/COMPANY/USER. **운영은 AWS Cognito**(User Pool, RS256/JWKS 검증, `AUTH_PROVIDER=cognito`)로 발급·검증 적용됨. 코드 기본값은 자체 HS256(`AUTH_PROVIDER=local`). 계정/조직 삭제는 **소프트 삭제**(status `INACTIVE` + Cognito disable) → 복원 → 영구삭제(purge) 3단계. auth 미들웨어가 `status != ACTIVE`면 401 차단.
- **A/B** UI 선반영, YouTube RAG 실기능은 최종 단계. **Chat** OpenAI gpt-4o-mini·CLIO·SSE — 오케스트레이터 본체(통합 딥에이전트, `deepagents` 기반, `api/assistant/deep_agent_builder.py`) **구현 완료**(`POST /api/chat/complete`). management·generator·simulation 3개 도메인 모두 **@tool 위임으로 연결**(deepagents 고유 서브에이전트 기능은 미사용, 커스텀 tool 라우팅).
- **Ad gen** 개선 시안 3개 자동생성+순위 (Gemini Flash 3.0 / GPT Image 2 / Gemini Omni). **PDF** 전체 생성 포함. **문의** in-app 폼 → DB.

## 핵심 기능 (기획서 v1.3)

| #   | 기능              | 설명                                          | 우선순위 |
| --- | ----------------- | --------------------------------------------- | -------- |
| 4-1 | 광고 시뮬레이터   | 집행 전 반응 예측 → 개선 방향·보고서          | 핵심(2인) |
| 4-2 | 광고 매니지먼트   | 목표·예산·플랫폼·성과를 단일 창구 관리        | 핵심(2인) |
| 4-3 | 광고 생성         | 예측 반영 → 개선 시안 3개 생성·기대성과 순위  | 핵심(2인) |
| 4-4 | 채팅 AI 어시스턴트 | 자유질문 + 시뮬·분석·생성 결과 전달          | 후순위    |

> 핵심 3기능 병렬 진행, 채팅(4-4)·팀 관리는 그 완료 후 착수.

**시뮬레이터 4대 KPI** — ① **클릭 의향률**: AISAS Action 통과 비율, 신뢰구간으로 표기 / **"예측 CTR" 등 실측 스케일 환산 금지**(실측 누적 후 calibration 해금). ② **구매의도**: 1~5점 평균+분포(분포 전체 표시, 평균 단언 금지). ③ **신뢰도**: 1~5점 평균. ④ **거부율**: 거부 비율 + 사유 분해.

## 로드맵 / 비즈니스

- **로드맵** 베이스라인 2026-06-12 ✅ → 최종 구현 2026-07-08(핵심 3기능 + 채팅·팀관리) → 발표 2026-07-14.
- **플랜(UI만, 실과금 추후)** Free(개인·제한 시뮬·트래킹 1개) / Professional(팀·확장·무제한 트래킹·API 연동) / Enterprise(기업·대규모·다채널).
- **조직** = 결제 단위(플랜 공유), **프로젝트** = 캠페인 단위(시안+매니지먼트), **팀 관리** = 프로젝트 협업(뷰어/에디터/오너).

## 인증 및 보안

- 소셜 로그인·자가가입 없음, **관리자가 직접 계정 생성**. 역할 ADMIN/COMPANY/USER.
- **운영 인증 = AWS Cognito.** `AUTH_PROVIDER=cognito`면 프론트가 Cognito(User Pool)로 로그인하고 백엔드가 ID 토큰(RS256, JWKS)을 검증(`core/auth.py`). `AUTH_PROVIDER=local`(코드 기본값)이면 자체 HS256 JWT 발급/검증. Cognito username = `login_id`, role → 동명 그룹(ADMIN/COMPANY/USER).
- **첫 로그인 비번 변경** — 발급 계정은 `must_change_password=true`. 로그인 후 첫 페이지에서 변경 모달을 계정당 1회만 노출(프론트 `localStorage: pwModalDismissed:{userId}`).
- **계정 상태(status)** ACTIVE·PENDING·INACTIVE. auth 미들웨어(`get_current_user`)가 `status != ACTIVE`면 401 차단. admin의 소프트 삭제가 `INACTIVE` + Cognito disable로 로그인만 막고 데이터는 보존.
- 기밀 데이터(예산·크리에이티브) 평문 로그 금지. 외부 플랫폼 API 키(Meta 등)는 암호화 저장(AES-256).
- admin API는 `/api/admin/*` 경로 프리픽스 + ADMIN 역할로 제한.

## Tech Stack

- **Frontend** Next.js(TS) + Tailwind (pnpm) / **Backend+AI** FastAPI + LangGraph (uv).
- **DB** NeonDB(PostgreSQL + pgvector, vector(1536)) / **비동기 잡** 인프로세스 async(asyncio) / **Storage** AWS S3.
- **Deploy** 단일 EC2 + Nginx / **CI/CD** GitHub Actions(Docker) / **Tracing** LangSmith / **Chat LLM** OpenAI gpt-4o-mini(`openai` chat.completions, SSE).

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

> 현황: generator·management·simulation 모두 `domain/` 이전 완료(simulation은 `domain/simulation/`·`api/routers/simulation/`). 이후 `domain/chat`·`domain/billing`도 추가됨(챗 오케스트레이터 본체는 `api/assistant/`).

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
OPENAI_API_KEY= / ANTHROPIC_API_KEY= / GEMINI_API_KEY=   # 채팅·CLIO=OpenAI(gpt-4o-mini). GEMINI는 예비.
DATABASE_URL=postgresql+asyncpg://user:pw@host/db?sslmode=require
AWS_ACCESS_KEY_ID= / AWS_SECRET_ACCESS_KEY= / AWS_REGION=ap-northeast-2
S3_BUCKET_NAME=
LANGCHAIN_TRACING_V2=true / LANGCHAIN_ENDPOINT=https://api.smith.langchain.com
LANGCHAIN_API_KEY= / LANGCHAIN_PROJECT=clickme
# 인증 — 로컬 기본은 local(자체 HS256), 운영은 cognito
AUTH_PROVIDER=local                    # local | cognito
COGNITO_REGION= / COGNITO_USER_POOL_ID= / COGNITO_APP_CLIENT_ID=   # AUTH_PROVIDER=cognito 일 때 필수
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_AUTH_PROVIDER=cognito      # 운영 빌드 기준(로컬은 local 가능)
NEXT_PUBLIC_COGNITO_REGION= / NEXT_PUBLIC_COGNITO_USER_POOL_ID= / NEXT_PUBLIC_COGNITO_CLIENT_ID=
```

> **GitHub Secrets(6개로 최소화)** — `AWS_ACCESS_KEY_ID`·`AWS_SECRET_ACCESS_KEY`(CI 전용 IAM User `clickme-ci`, ECR push) · `EC2_HOST`(Elastic IP) · `EC2_SSH_KEY`(PEM 전체) · `OPENAI_API_KEY` · `E2E_DATABASE_URL`. 그 외 `AWS_REGION=us-west-2`·`EC2_USER=ubuntu`·`NEXT_PUBLIC_COGNITO_*`(User Pool `us-west-2_iHteTHXO0` 등)는 비밀이 아니라 워크플로에 평문으로 둔다.

## CI/CD 현황

- 구 `ci.yml`+`cd.yml`은 **단일 `.github/workflows/ci-cd.yml`로 병합**됨(구 파일 삭제).
- **needs 체인** `backend`(ruff + pytest)·`frontend`(ESLint + build) → `build-backend`·`build-frontend`(ECR push) → `deploy`(EC2). 빌드·배포는 CI 성공을 depends on하므로 테스트 실패 시 배포 차단.
- **트리거** PR(`main`·`ci-cd`)은 **테스트만**, `push`(`main`·`ci-cd`)만 build/deploy 실행(`if: github.event_name == 'push'`). e2e(Playwright)는 `workflow_dispatch` 수동.
- **배포** ECR 이미지(`clickme-backend`·`clickme-frontend`, `:latest`+`:${sha}`) → EC2에서 `docker-compose.prod.yml`로 기동. Nginx + Let's Encrypt(certbot 자동 발급·갱신). ECR push는 CI IAM User, pull은 EC2 IAM Role로 권한 분리.
- 인프라 상세는 [`infra/README.md`](infra/README.md) 참고(provision/resize/fetch_key 스크립트, Elastic IP 고정, PEM SSM 백업).

## 개발 워크플로우 (Claude 행동 규칙)

**커밋 컨벤션** `타입: 한국어 설명` — `add`(새 기능/파일) · `delete`(삭제) · `edit`(수정/리팩토링) · `fix`(버그). 예: `add: 시뮬레이션 기능 추가`.

**① 백엔드 .py 수정 직후 (IMPORTANT)** — 커밋 메시지 출력 **전에** Ruff 실행을 제안한다: *"백엔드 코드가 변경됐어요. 커밋 전에 Ruff로 맞춰두면 CI에서 안 막혀요. Ruff 실행할까요?"*
- 수락(응/해줘/yes/ㅇㅇ) → `cd backend && uv run ruff format . && uv run ruff check . --fix` 실행.
- 거절(나중에/ㄴㄴ) → 바로 커밋 메시지로. **프론트(TS)만 수정 시 생략.**
- 왜: CI(`ci-cd.yml`)가 `ruff check`로 검증. 로컬 선통과 안 하면 push 후 CI 실패. (pytest는 느리고 비용↑이라 별개.)

**② 구현 완료 시** — `타입: 설명` + 변경 불릿 형태의 커밋 메시지와 `git add . && git commit -m "…"`를 출력. 사소한 작업도 출력, 여러 기능은 기능별로 분리 제안.

**③ GitHub Issue 요청 시** — 먼저 `gh --version`으로 설치 확인. 미설치면 OS별 설치 안내(winget `GitHub.cli` / brew `gh` / apt `gh` → `gh auth login`) 후 `gh issue create` 제공. label은 `enhancement`/`bug`/`refactor`/`chore` 중 선택.

**④ Issue 일괄 생성 스크립트** — 반드시 **Python(`.py`)** 으로 제공(`.ps1`/`.sh` 금지). 백엔드에 포함된 `httpx`로 GitHub REST API(`POST /repos/{repo}/issues`, `Bearer` 토큰) 호출, `uv run python create_issues.py` 실행.

**⑤ 테스트·검증 요청 시 (IMPORTANT)** — "테스트 돌려줘 / 확인해줘" 류 요청이면 Ruff·pytest·E2E뿐 아니라, **브라우저에서 확인 가능한 변경(프론트·백엔드 화면/응답)이면 Claude Preview(`preview_*` 도구)로 실제 화면을 띄워 유저가 눈으로 볼 수 있게 하는 검증**도 함께 제안한다: *"실제 화면도 Claude Preview로 띄워서 동작을 보여드릴까요?"*
- 수락(응/해줘/yes/ㅇㅇ) → `preview_start`로 dev 서버를 띄우고 `preview_*` 도구로 동작을 관찰한 뒤, 스크린샷·콘솔/네트워크 로그·스냅샷을 **증거로 공유**한다. "이걸 눌러보세요" 식 수동 체크리스트로 떠넘기지 않는다.
- 거절(나중에/ㄴㄴ) → Ruff·pytest·E2E 등 기존 검증만.
- 왜: 화면으로 확인되는 변경은 유저가 결과를 직접 보는 게 가장 확실. 브라우저로 확인 불가한 변경(타입·툴링·순수 로직)이면 제안을 생략한다.

**⑥ 엔드포인트/페이지 추가 시 문서 자동 동기화 (IMPORTANT)** — 라우터(`backend/api/`)나 페이지(`frontend/src/app/`)를 추가·삭제·경로 변경하면 **`docs/api-endpoints.md`·`docs/frontend-routes.md`·CLAUDE.md의 AUTOGEN 구간**을 다시 생성해야 한다.
- 생성기 `cd backend && uv run python scripts/gen_docs.py` (검사만: `--check`, CI drift용). 이 세 파일은 **자동 생성물이라 손으로 고치지 말 것** — 소스를 고치고 재실행.
- 커밋 시 pre-commit 훅이 자동 실행·스테이징한다(설치 1회: `git config core.hooksPath .githooks`). 미설치·실패 시에도 CI(`ci-cd.yml` backend 잡의 *Docs drift check*)가 어긋나면 빌드를 막는다.
- API의 요청/응답 스키마 등 상세 설명은 여전히 수기 문서 `docs/api-spec.md`에 둔다(자동 목록과 역할 분리).

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
| 비동기 잡 큐 도입 여부              | 현재 인프로세스 async(asyncio). SQS·Redis 모두 미사용 — 운영 확장 시 재검토. |
| 인증 실구현 (JWT 자체 vs Cognito)   | **해소** — 운영은 AWS Cognito(User Pool, RS256/JWKS 검증) 적용, 코드 기본값은 자체 HS256(`AUTH_PROVIDER`로 전환). 남은 과제는 리프레시 토큰·세션 만료 정책 정리. |
| 채팅(4-4) 오케스트레이터 배선 정리   | 오케스트레이터 본체(통합 딥에이전트)는 구현 완료, management·generator·simulation 전부 @tool로 연결됨(2026-06-30, `4c3e7c8`). `domain/chat/__init__.py` 설명이 실제 구현 위치(`api/assistant/`)와 어긋나 문서 정리 필요. |
| CD 활성화                           | **해소** — `ci-cd.yml` 병합 파이프라인이 ECR push → EC2 배포까지 자동화(Secrets 6개 등록 완료). 남은 과제는 무중단 롤아웃·롤백 전략. |

## Reference

**자동 생성 인덱스**(라우터·페이지 추가 시 `backend/scripts/gen_docs.py`가 갱신 — 직접 수정 금지):

<!-- AUTOGEN:docs-index START -->
- **API 엔드포인트 186개** — 전체 목록 [docs/api-endpoints.md](docs/api-endpoints.md) (자동 생성)
- **프론트 라우트 42개** — 전체 목록 [docs/frontend-routes.md](docs/frontend-routes.md) (자동 생성)
<!-- AUTOGEN:docs-index END -->

- API 명세(수기) → `docs/api-spec.md` / 자동 엔드포인트 목록 → `docs/api-endpoints.md` / 프론트 라우트 → `docs/frontend-routes.md`.
- DB 스키마·Alembic → `docs/db-schema.md` / 실 DB ERD(introspection) → `docs/db-erd.md`.
- **PM 규칙** pnpm은 `backend/` 금지, uv는 `frontend/` 금지.
- **Dev** 백엔드 `cd backend && uv run uvicorn api.main:app --reload --port 8000` / 프론트 `cd frontend && pnpm dev` / 전체 `docker compose up --build` / 테스트 `cd backend && uv run pytest tests/ -v`.
