# ClickMe — CLAUDE.md

> 집행 전 AI 가상 소비자에게 광고를 테스트하고, 집행 후 성과를 추적·관리하는 **광고 전주기 지원 플랫폼** (기획서 v1.3).
> 목표는 "실제 사람과 동일한 응답"이 아니라 "직감·내부 검토보다 나은 의사결정 근거" 제공.

## Key Decisions

- **Backend** FastAPI (Python only, No Spring) / **PM** uv(backend)·pnpm(frontend) 교차 금지 / **Arch** 모놀리식 + 부분 DDD/SOLID, 단일 EC2.
- **비동기 잡** 인프로세스 async(`asyncio.create_task`) + **APScheduler 워커**(management: 이상 스캔·리밸런스 제안·주간 리포트 / generator: 품질 다이제스트; 기본 off, `*_SCHEDULER_ENABLED` 플래그로 on). 관측·집계·기록은 워커 자율, **집행 write는 사람 승인(HITL)**. 별도 MQ 미사용 — SQS·Redis 모두 안 씀.
- **Sim engine** OCEAN 5요인 조건부 페르소나 샘플링(서울대-카카오 OCEAN N=81만·KISDI 미디어 실데이터; 행안부 인구는 확보 예정). **Scoring** 현재 LLM 루브릭(정합)+페르소나 반응 LLM+부트스트랩 신뢰구간 집계 — **SSR(임베딩 기반, arXiv 2510.08338) 전환은 데이터 확보 후**(구 `tools/simulation/ssr_scorer` 보존). **Output** 스칼라 아닌 분포.
- **구매의도 검증** KOBACO 베이스라인 대비(현재 챗봇 룩업으로 참고 제시, 실측 대비 자동 calibration은 **연결 캠페인 실측 5건 이상 확보 시 해금 예정**). 그 외 신호는 탐색적(exploratory) 표기.
- **인증** AWS Cognito 기반 JWT(JWKS RS256 검증) **운영 중** + 관리자 직접 계정 생성(`cognito_admin`, 자가가입·소셜 없음), Admin/User 역할. 자체 local JWT 모드는 예비(로그인 발급 라우터 미완).
- **A/B** UI 선반영, YouTube RAG 실기능은 최종 단계. **Chat** OpenAI gpt-4o-mini·CLIO·SSE — 오케스트레이터 본체(통합 딥에이전트, `deepagents` 기반, `api/assistant/deep_agent_builder.py`) **구현 완료**(`POST /api/chat/complete`). management·generator·simulation 3개 도메인 모두 **@tool 위임으로 연결**(deepagents 고유 서브에이전트 기능은 미사용, 커스텀 tool 라우팅).
- **멀티 LLM 역할 배정** 채팅 gpt-4o-mini · 시뮬 반응 Gemini 2.5 Flash · 페르소나 토론 토론자 gpt-4o-mini/Judge Claude Haiku · 생성 gpt-4.1.
- **Ad gen** 시안 3종 자동생성+QA 기반 순위(개선 모드는 1종). 모델은 config 교체(`GENERATOR_*_MODEL`) — 현재 기본값 텍스트 gpt-4.1·비전 gpt-4o·이미지 gpt-image-1(OpenAI 모드)/gemini-2.5-flash-image(Gemini 모드). **PDF** 전체 생성 포함. **문의** in-app 폼 → DB.

## 핵심 기능 (기획서 v1.3)

| #   | 기능               | 설명                                         | 우선순위  |
| --- | ------------------ | -------------------------------------------- | --------- |
| 4-1 | 광고 시뮬레이터    | 집행 전 반응 예측 → 개선 방향·보고서         | 핵심(2인) |
| 4-2 | 광고 매니지먼트    | 목표·예산·플랫폼·성과를 단일 창구 관리       | 핵심(2인) |
| 4-3 | 광고 생성          | 예측 반영 → 개선 시안 3개 생성·기대성과 순위 | 핵심(2인) |
| 4-4 | 채팅 AI 어시스턴트 | 자유질문 + 시뮬·분석·생성 결과 전달          | 후순위    |

> 핵심 3기능 병렬 진행, 채팅(4-4)·팀 관리는 그 완료 후 착수.

**시뮬레이터 4대 KPI** — ① **클릭 의향률**: AISAS Action 통과 비율, 신뢰구간으로 표기 / **"예측 CTR" 등 실측 스케일 환산 금지**(실측 누적 후 calibration 해금). ② **구매의도**: 1~5점 평균+분포(분포 전체 표시, 평균 단언 금지). ③ **신뢰도**: 1~5점 평균. ④ **거부율**: 거부 비율 + 사유 분해.

## 로드맵 / 비즈니스

- **로드맵** 베이스라인 2026-06-12 ✅ → 최종 구현 2026-07-08(핵심 3기능 + 채팅·팀관리) → 발표 2026-07-14.
- **플랜** Free(개인·제한 시뮬·트래킹 1개) / Professional(팀·확장·무제한 트래킹·API 연동) / Enterprise(기업·대규모·다채널). **결제** Toss Payments 연동 PoC(샌드박스 테스트키 전용, 실 과금 미개시).
- **조직** = 결제 단위(플랜 공유), **프로젝트** = 캠페인 단위(시안+매니지먼트), **팀 관리** = 프로젝트 협업(뷰어/에디터/오너).

## 인증 및 보안

- 소셜 로그인·자가가입 없음, **관리자가 직접 계정 생성**. **AWS Cognito JWT**(JWKS RS256) 기반, Admin/User 역할.
- **Meta 매니지먼트** 성과 읽기 실연동 + 감지→진단→승인→집행→감사 통제 집행 파이프라인. writer는 DRY_RUN/VALIDATE/LIVE 3모드로 **기본 봉인**(집행 write는 사람 승인).
- 기밀 데이터(예산·크리에이티브) 평문 로그 금지. 외부 플랫폼 API 키는 암호화 저장(AES-256 또는 AWS Secrets Manager).
- 현재 페이즈: admin API는 `/api/admin/*` 경로 프리픽스로만 제한.

## Tech Stack

- **Frontend** Next.js(TS) + Tailwind (pnpm) / **Backend+AI** FastAPI + LangGraph (uv).
- **DB** NeonDB(PostgreSQL + pgvector, vector(1536)) / **RAG** 하이브리드 검색(pgvector 코사인 + PostgreSQL FTS 키워드, RRF 융합) for management·generator KB / 장기기억 회수 tsvector 키워드 / CLIO 일반지식 벡터 전용 / **비동기 잡** asyncio + APScheduler / **Storage** AWS S3.
- **Deploy** 단일 EC2 + Nginx / **CI/CD** GitHub Actions — CI(ruff·pytest·lint·build) + **CD 활성**(main push → ECR 빌드/푸시 → EC2 배포 → Let's Encrypt TLS 자동갱신) / **Tracing** LangSmith / **Chat LLM** OpenAI gpt-4o-mini(SSE).

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

> 이전 현황: generator·management·**simulation 모두 `domain/` 이전 완료**(등록 라우터는 `api/routers/simulation/`). 구 평면 라우터 `api/routers/simulate.py`는 **삭제 대상**(미등록 데드코드), `tools/simulation/`(ssr_scorer 등)은 **SSR 전환 대비 보존**.

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
OPENAI_API_KEY= / ANTHROPIC_API_KEY= / GEMINI_API_KEY=   # OpenAI(채팅·CLIO·생성 기본·토론자) · Gemini(시뮬 반응·이미지) · Anthropic(토론 Judge Haiku).
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

- **CI** (`ci.yml`) ✅ — `backend`(ruff + pytest), `frontend`(ESLint + build) 활성 / `docker-build` ⏸(Secrets 후 활성).
- **CD** (`cd.yml`) ✅ — **활성**. `main` push → ECR 빌드/푸시(backend+frontend) → EC2 SSH 배포 → Let's Encrypt TLS 최초발급/자동갱신 → `docker compose up`. 도메인 clickme.co.kr TLS 구성 완료.

## 개발 워크플로우 (Claude 행동 규칙)

**커밋 컨벤션** `타입: 한국어 설명` — `add`(새 기능/파일) · `delete`(삭제) · `edit`(수정/리팩토링) · `fix`(버그). 예: `add: 시뮬레이션 기능 추가`.

**① 백엔드 .py 수정 직후 (IMPORTANT)** — 커밋 메시지 출력 **전에** Ruff 실행을 제안한다: _"백엔드 코드가 변경됐어요. 커밋 전에 Ruff로 맞춰두면 CI에서 안 막혀요. Ruff 실행할까요?"_

- 수락(응/해줘/yes/ㅇㅇ) → `cd backend && uv run ruff format . && uv run ruff check . --fix` 실행.
- 거절(나중에/ㄴㄴ) → 바로 커밋 메시지로. **프론트(TS)만 수정 시 생략.**
- 왜: CI(`ci-cd.yml`)가 `ruff check`로 검증. 로컬 선통과 안 하면 push 후 CI 실패. (pytest는 느리고 비용↑이라 별개.)

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
| 비동기 잡 큐 도입 여부              | 현재 인프로세스 async(asyncio) + APScheduler 워커. SQS·Redis 미사용 — 운영 확장 시 재검토. |
| local JWT 모드 완성 여부            | 운영은 Cognito로 확정·배선 완료. 자체 local JWT는 로그인 발급 라우터 미완(예비) — 완성 시점 미정. |
| 구 오케스트레이터 데드코드 제거      | 통합 딥에이전트로 전환 완료. 구세대 `orchestrator.py`·`intent.py`·`registry.py`는 테스트만 참조하는 데드코드 → **발표 후 삭제**(`wiring.py`의 `_build_*_handler`는 통합 에이전트가 재사용하므로 보존). `domain/chat/__init__.py` docstring도 실제 역할(지원 인프라)로 정리 필요. |
| 매니지먼트 집행 모드 안전(발표 전)   | 커밋된 `backend/.env`가 `MANAGEMENT_EXECUTION_MODE=live`+`USE_MOCK=false`+실 토큰 → 실 Meta 집행·과금 가능. 파일 내 주석("dry_run 유지")과 모순. **데모/발표 전 `dry_run` 복귀 필요.** |

## Reference

**문서 인덱스**(라우터·페이지 추가 시 `backend/scripts/gen_docs.py`가 아래 두 목록을 갱신 — 직접 수정 금지):

- **API 엔드포인트** — 전체 목록 [docs/api-endpoints.md](docs/api-endpoints.md) (자동 생성)
- **프론트 라우트** — 전체 목록 [docs/frontend-routes.md](docs/frontend-routes.md) (자동 생성)

- API 명세(수기) → `docs/api-spec.md` / 자동 엔드포인트 목록 → `docs/api-endpoints.md` / 프론트 라우트 → `docs/frontend-routes.md`.
- DB 스키마·Alembic → `docs/db-schema.md` / 실 DB ERD(introspection) → `docs/db-erd.md`.
- **PM 규칙** pnpm은 `backend/` 금지, uv는 `frontend/` 금지.
- **Dev** 백엔드 `cd backend && uv run uvicorn api.main:app --reload --port 8000` / 프론트 `cd frontend && pnpm dev` / 전체 `docker compose up --build` / 테스트 `cd backend && uv run pytest tests/ -v`.
