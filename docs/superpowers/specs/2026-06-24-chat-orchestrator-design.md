# 챗 오케스트레이터 설계 (4-4)

> 사용자가 프롬프트 하나로 시뮬·생성·매니지먼트를 가로질러 **실행 + 근거 제시 + 집행**까지 받는 통합 워크플로우 관리자. 본 문서는 브레인스토밍으로 확정한 설계(spec)이며, 다음 단계는 writing-plans로 구현 계획 작성이다.

## 1. 목표 / 비목표

**목표 (v1)**
- 단일 챗 입력 → 의도 파악 → 적절한 도메인(시뮬/생성/매니지먼트)으로 라우팅 → **읽기(결과·근거) + 집행(시뮬 실행·시안 생성·캠페인 집행)** 수행.
- 집행은 기존 매니지먼트 **단일 지출 경로(approve→execute)+Tier 정책+HITL**을 재사용. 챗은 새 지출 경로를 만들지 않는다.
- 멀티스텝 자율 추론(예: "시뮬 돌려보고 결과 좋으면 시안 생성").
- 모든 대화를 **단일 챗 스키마**에 영속, 어느 서브에이전트가 답했는지 태깅.

**비목표 (후순위)**
- MCP 외부 서버 노출(ClickMe를 외부 LLM 클라이언트에 도구로 개방) — 별도 과제.
- A/B·YouTube RAG 실기능, calibration 해금.
- 챗 전용 새 결제/지출 경로(기존 것만 호출).

## 2. 확정 결정 (브레인스토밍)

| 항목 | 결정 |
|---|---|
| v1 범위 | 전 도메인 읽기+집행 |
| 아키텍처 | LangGraph **슈퍼바이저 + 도메인 서브에이전트** |
| HITL 승인 | **챗 인라인** (그래프 interrupt → 승인 카드 → 재개) |
| 슈퍼바이저 LLM | **Claude Sonnet 4.6** (`claude-sonnet-4-6`), 서브에이전트는 기존 모델 유지, 설정화 |
| 전송 | **SSE 유지**, MCP는 후순위 |
| 챗 영속 | 단일 `chat_*` + `route` 컬럼, `management_chat_*` 흡수 후 정리 |
| 임베딩 | **BGE-M3**(로컬, 1024) via `EmbeddingProvider` 포트(설정 교체). KB·LTM 공유 |
| 메모리 | **3계층** — 숏텀(messages+checkpoints) / 롱텀(임베딩 LTM) / KB |
| 구현 순서 | ① 기반 정합 → ② 정리 DROP → ③ 오케스트레이터 |

## 3. 아키텍처 — 새 바운디드 컨텍스트 `domain/chat/`

오케스트레이터는 도메인을 가로지르므로 타 도메인을 **공개 진입점(contracts/서비스)으로만** 소비하는 별도 컨텍스트로 둔다(CLAUDE.md 도메인 경계 규칙 준수, 내부 직접 import 금지).

```
backend/domain/chat/
├── contracts/   ChatTurnRequest · ChatEvent · Intent · SubAgentResult 스키마
│                + SubAgent(Protocol) · ChatRepo(Protocol) · MemoryStore 포트
├── adapters/    ManagementSubAgent(→ build_management_agent)
│                SimulationSubAgent(→ build_simulation_service)
│                GeneratorSubAgent(→ generator_service / D1)
│                PgChatRepo · PgMemoryStore · 브랜드 어댑터
├── graph/       LangGraph 슈퍼바이저 그래프 (state·nodes·edges)
├── service/     ChatOrchestratorService (SSE 스트리밍·세션/메모리 영속 지휘)
└── wiring.py    Composition Root (서브에이전트·checkpointer·repo·LLM 주입)
```

- `api/routers/chat.py`는 얇게 재작성 → `ChatOrchestratorService`만 호출. 기존 키워드 라우팅(`_MGMT_KEYWORDS`) 제거.
- 의존 방향 `api/routers/chat → domain/chat/service → contracts(포트) ← adapters(구현)`. mock↔실연동은 `domain/chat/wiring.py`에서만.

## 4. 슈퍼바이저 그래프

상태(State) 주요 필드 — `messages`(대화), `route`(현재 위임 도메인), `sub_results`(서브에이전트 산출), `pending_action`(집행 대기), `citations`, `thread_id`.

```
load_context  숏텀(최근 메시지+요약) + 롱텀(LTM 임베딩 top-k 회상) + 브랜드 프로필 적재
   │
supervisor    Claude Sonnet 4.6 tool-calling:
   │          [route_to_simulation, route_to_generation, route_to_management, answer_directly]
   │          (멀티스텝: 한 턴에 여러 서브에이전트 연쇄 위임 허용)
   ├─ answer_directly → synthesize
   └─ route_to_* → delegate
delegate      선택된 SubAgent 실행 → SubAgentResult(answer, citations, proposed_action?) 반환
   │
   ├─ proposed_action 없음 → (필요시 supervisor 재진입) → synthesize
   └─ proposed_action 있고 Tier 정책상 승인 필요 → interrupt
interrupt     그래프 정지(HITL). thread_id로 체크포인트 영속. SSE로 approval_request 송신
   │  (사용자 승인/거부 → resume)
execute       승인 시 매니지먼트 단일 경로(approval→executor)로 집행 → 결과 수집
   │
synthesize    답변 + 근거(citations) + 구조화 결과 합성(CLIO 보이스) → 영속(chat_messages)
```

- **라우팅 품질** — 슈퍼바이저는 도구 설명 + few-shot으로 도메인 의도를 판별. 결정론 폴백(키 없음/저신뢰) = 기존 키워드 매칭.
- **루프 가드** — 서브에이전트 연쇄 호출 최대 횟수 제한(예: 4)으로 무한루프 차단.

## 5. 서브에이전트 통합 (경계 준수)

각 도메인을 `SubAgent` 포트로 추상화, `wiring.py`에서 실제 진입점 주입. 오케스트레이터는 포트에만 의존한다.

| 서브에이전트 | 래핑 대상(기존 자산) | 능력 |
|---|---|---|
| management | `domain/management/assistant/agent.py:build_management_agent` (이미 LangGraph ReAct + KB + HITL) | 캠페인/예산/성과 읽기, 진단, 집행 제안, KB(`management_kb_chunks`) |
| simulation | `domain/simulation/wiring.py:build_simulation_service` | 시뮬 결과·KPI 읽기, 새 시뮬 트리거 |
| generation | `domain/generator/service/generator_service.py` + D1 계약 | 시안 생성/조회 |

- 교환은 `domain/chat/contracts`의 `SubAgentResult`(+ 매니지먼트는 기존 `AskRequest/AskResult` 재사용)로만.
- 매니지먼트 서브에이전트는 **자기 챗 영속을 하지 않고** 결과만 반환(§6 수렴).

## 6. 영속 · 스키마 수렴

### 6.1 메모리 3계층 모델

| 계층 | 무엇 | 저장소 | 회상 방식 |
|---|---|---|---|
| 숏텀(작업) | 현재 대화 + 그래프 실행 상태 | `chat_messages`(정규화 행) + `checkpoints*`(LangGraph 스레드 상태) | 최근 N개/토큰 윈도우, 오래된 턴은 요약 압축 |
| 롱텀(기억) | 세션 넘는 사용자/프로젝트 사실·선호·결정 | `chat_long_term_memory` | **임베딩 top-k** + 고salience 항상로드 |
| 지식(KB) | 공유 정책·플레이북(사용자 메모리 아님) | `management_kb_chunks` | 임베딩 top-k |

- 숏텀은 최근성 기반(임베딩 불필요), 길어지면 `chat_sessions.summary`(롤링 요약)로 압축해 토큰 윈도우 유지.
- 롱텀은 턴 후 reflection 단계가 '기억할 가치'를 추출해 임베딩과 함께 적재 → 다음 세션에서 의미로 회상. **임베딩 모델은 KB와 동일**(BGE-M3, §9).
- KB는 사용자 메모리와 구분되는 도메인 지식. 세 계층은 섞지 않는다.

### 6.2 스키마 수렴·변경

대화 저장이 두 벌(`chat_*` 범용 + `management_chat_*` 어시스턴트)로 중복이고, 실 테이블에 구멍이 있다 — `chat_sessions.messages` jsonb ↔ `chat_messages` 행 **이중화**, `chat_long_term_memory`에 **embedding 없음**(의미 회상 불가), 세션에 user_id·요약 없음. **단일 `chat_*`로 수렴하며 아래를 변경한다.**

| 테이블 | 처리·변경 |
|---|---|
| `chat_sessions` | KEEP·정본. `messages` jsonb **제거**(이중화 해소), **user_id·organization_id·title·summary 추가** |
| `chat_messages` | KEEP·정본. **`route` 컬럼 추가**('general'\|'management'\|'simulation'\|'generation'), session_id FK 부여 |
| `chat_long_term_memory` | KEEP. **`embedding vector(1024)`·salience·last_used_at·source_session_id 추가**(의미 회상용) |
| `chat_brand_profiles` | `brand_profiles`와 비교 후 통합 검토(구조화 always-load 프로필) |
| `management_chat_sessions`·`management_chat_messages`·`management_agent_runs` | 통합 `chat_*`로 흡수 → **정리(②) 대상**. 테스트 데이터는 이관/폐기 |
| `management_kb_*`(documents/eval_cases/feedback) | KEEP — 어시스턴트 RAG 지식(KB 계층) |
| `checkpoints`·`checkpoint_blobs`·`checkpoint_writes`·`checkpoint_migrations` | LangGraph `AsyncPostgresSaver` 관리. `wiring.build_checkpointer`를 MemorySaver→AsyncPostgresSaver 전환 |

- 오케스트레이터가 모든 메시지를 `chat_messages`에 `route` 태깅해 단일 기록. 매니지먼트 어시스턴트는 영속 책임 제거.

## 7. 집행 · HITL

- 기존 **Tier 정책**(`domain/management/contracts/policy.py`) 그대로 — Tier0~1 자율, Tier3(캠페인 집행 등) 사람 승인.
- 위험 액션 제안 시 그래프 `interrupt` → `AsyncPostgresSaver`로 thread 영속 → SSE `approval_request` → 사용자 승인 → `POST /api/chat/{thread_id}/resume` → 그래프 재개 → 매니지먼트 `executor`(멱등키·감사·소프트캡) 단일 경로 집행.
- 재시작 후에도 체크포인터로 미결 승인 재개 가능.

## 8. SSE 이벤트 프로토콜

기존 `chat.py` SSE(threading + asyncio.Queue) 패턴 확장. 프레임 = `data: {json}\n\n`.

| type | 페이로드 | 용도 |
|---|---|---|
| `meta` | route, source, thread_id, requires_approval | 턴 시작 메타 |
| `tool_status` | agent, state, label | 어느 서브에이전트 실행 중 |
| `token` | text | 답변 토큰 스트리밍 |
| `result` | kind, data | 구조화 근거(예: simulation_aggregate) |
| `approval_request` | tier, action, thread_id | HITL 승인 카드 |
| `error` | message | 오류 |
| `done` | finish_reason | 종료 |

프론트(`frontend/src/app/chat/page.tsx`) — `meta`로 배지, `approval_request`로 승인/거부 카드 렌더 + resume 호출 추가.

엔드포인트 — `POST /api/chat/complete`(SSE, 기존 확장), `POST /api/chat/{thread_id}/resume`(승인 재개, 신규), `GET /api/chat/sessions`·`/sessions/{id}/messages`(영속 연결, 기존 스텁 채움).

## 9. LLM · 설정

- 슈퍼바이저 = `claude-sonnet-4-6` (`init_chat_model` 또는 `ChatAnthropic`, tool-calling). 설정 키 `CHAT_ORCHESTRATOR_MODEL`/`_PROVIDER`.
- 서브에이전트 = 기존 모델 유지(매니지먼트 GPT-4o-mini 등). "브레인은 강하게, 일꾼은 싸게."
- CLIO 페르소나는 synthesize 단계 보이스로 유지.
- 키 없으면 결정론 폴백(키워드 라우팅 + 읽기 전용).
- **임베딩** = `EmbeddingProvider` 포트로 추상화(LLM 팩토리와 동형). 기본 **BGE-M3**(로컬, 1024차원), 설정 키 `EMBEDDING_PROVIDER`/`_MODEL`. KB·LTM이 **동일 모델·차원** 공유(혼용 불가).
- **임베딩 서빙** = 단일 EC2에 TEI(text-embeddings-inference) 또는 Ollama `bge-m3` 사이드카(저 QPS면 CPU 감내). 설정으로 OpenAI `text-embedding-3-small`(1536) 폴백 전환 가능.

## 10. 에러처리 · 테스트

- 서브에이전트 실패 → graceful 메시지 + 폴백. 503 벤더 리스크는 기존 동시성 제한·폴백 패턴 재사용.
- HITL은 checkpointer 영속이라 프로세스 재시작 후 재개 가능.
- 테스트(hermetic, USE_MOCK) — 슈퍼바이저 라우팅(mock 서브에이전트), 어댑터 계약 적합성, interrupt/resume(checkpointer), `PgChatRepo`(sqlite), SSE 프레임 순서.

## 11. 구현 단계 (전체 "전부" 매핑)

**Phase ① 기반 정합 (선결)**
- 보류 챗 테이블(`chat_*`·`checkpoints*`·`management_kb_*`)을 repo로 공식화 — ORM(`domain/chat/models.py` 또는 core) + Alembic 022+ 마이그레이션. 실 DB 스탬프(024) 드리프트 정합.
- `regeneration_jobs`(ORM 있음·실DB 없음), `ads`/`projects`/`simulations` ORM 드리프트 동기화([db-cleanup.md](../../db-cleanup.md) §컬럼).
- 산출 = repo ORM/마이그레이션 ≈ 실 DB의 깨끗한 베이스라인.

**Phase ② 정리 DROP**
- 안전 후보(generated_ads·simulation_results·audit_logs·simulation_comparisons·persona_templates·project_members·user_settings·subscription_plans·organization_subscriptions·benchmarks·calibration_data·ad_templates·generator_kb_chunks·rag_chunks·simulation_kb_chunks·diagnoses·recommendations·reports + 수렴된 management_chat_*·management_agent_runs) 삭제. ①과 같은 마이그레이션 세트.

**Phase ③ 오케스트레이터 구현**
- `domain/chat/` 신설(contracts·adapters·graph·service·wiring), 슈퍼바이저 그래프, 서브에이전트 어댑터 3종, SSE 확장, resume 엔드포인트, AsyncPostgresSaver 전환, 프론트 승인 카드.

## 12. 리스크 / 열린 질문

- **3중 드리프트** — 실 DB(024) ≠ 레포(021) ≠ ORM. Phase ①이 이걸 정합하지 않으면 마이그레이션이 충돌. 개인 복제본에서 먼저 검증, 공용 DB 적용 전 재확인.
- **AsyncPostgresSaver 마이그레이션** — checkpoints* 테이블 스키마를 LangGraph 라이브러리 버전(현 `langgraph-checkpoint` 4.1.1)에 맞춰야 함. 라이브러리 `.setup()`으로 생성할지 마이그레이션으로 박을지 결정 필요.
- **임베딩 전환(1536→1024)** — BGE-M3로 가면 pgvector 차원 변경 + 기존 벡터 재임베딩 + 인덱스 재생성. 모든 벡터 테이블이 한 모델 공유해야 비교 가능. 벡터 데이터가 빈 지금이 전환 최저 비용. 로컬 서빙은 단일 EC2 RAM/CPU(또는 GPU) 점유 — 지연·자원 경합 점검 필요.
- **LTM 추출 품질** — 무엇을 장기기억으로 남길지(reflection) 정밀도가 낮으면 노이즈 누적. salience 기준·상한 필요.
- **시뮬 트리거의 장시간성** — 시뮬은 SSE 진행률이 길다. 챗 턴 안에서 동기 대기 vs 비동기 시작+나중 결과 알림 정책 결정 필요.
- **`chat_brand_profiles` vs `brand_profiles`** — 컬럼 비교 후 통합/유지 확정.
- **라우팅 신뢰성** — 슈퍼바이저 오라우팅 측정·완화(few-shot, 폴백) 평가 하니스 필요.

## 13. 기술 스택

이 설계에 적용되는 기술. (★ = 이번 오케스트레이터에서 새로 도입/전환, 나머지는 기존 자산 재사용)

| 영역 | 기술 | 용도 |
|---|---|---|
| 백엔드 | **FastAPI** + Uvicorn (pkg: uv) | SSE 엔드포인트·라우터(`api/routers/chat.py`) |
| 오케스트레이션 | **LangGraph** (`langgraph>=0.2`) | 슈퍼바이저 StateGraph, `interrupt`(HITL) |
| 체크포인터 | **langgraph-checkpoint `AsyncPostgresSaver`** ★ | HITL thread 영속(`checkpoints*` 테이블). 현 `MemorySaver`에서 전환 |
| 슈퍼바이저 LLM | **Claude Sonnet 4.6** (`claude-sonnet-4-6`) ★ via `langchain-anthropic`/`anthropic` SDK | 의도 라우팅·멀티스텝 계획·tool-calling |
| 서브에이전트 LLM | GPT-4o-mini (`langchain-openai`, 매니지먼트) · Gemini (`google-generativeai`, CLIO 보이스) | 도메인 실행·합성 보이스 |
| LLM 통합 | **LangChain** (`init_chat_model`), langchain-openai/anthropic/google-genai | 프로바이더 교체 추상화(설정화) |
| RAG·벡터 | **pgvector** `vector(1024)` + **BGE-M3**(로컬) ★ via `EmbeddingProvider` 포트 + `cosine_distance`. 서빙 TEI/Ollama, OpenAI 폴백 | KB + 롱텀 메모리 의미 검색 |
| DB | **NeonDB(PostgreSQL 18) + pgvector** / SQLAlchemy 2.x async(`asyncpg`) / `psycopg2`(alembic) / **Alembic** | 챗 영속(`chat_*`)·스키마 정합 |
| 스트리밍 | **SSE** (FastAPI `StreamingResponse` + threading/`asyncio.Queue` 브릿지) | 토큰·tool_status·approval_request 실시간 전송 |
| 관측 | **LangSmith** (트레이싱 + 기밀 redaction) | 그래프·LLM 호출 추적 |
| 복원력 | **tenacity**(지수 백오프) + 동시성 제한·폴백 | 503 벤더 리스크 완충 |
| 인증 | python-jose(JWT) + bcrypt (기존) | 세션 주체·권한 |
| 프론트 | **Next.js(TS) + Tailwind** (pkg: pnpm), fetch+ReadableStream SSE 파싱 | `/chat` UI + 승인 카드 ★ |
| 설계 패턴 | **DDD + 헥사고날**(ports/adapters), Composition Root(`wiring.py`), contracts-only 도메인 교환 | `domain/chat/` 경계 |
| 개발 도구 | uv · pytest(+asyncio) · ruff | 의존성·테스트·린트 |

**미채택(후순위)** — MCP(외부 LLM 클라이언트 노출), Redis(트래킹 큐), SQS 챗 비동기 처리. v1 범위 밖.
