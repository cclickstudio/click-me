# 채팅 ↔ 매니지먼트 실행·재생성 핸드오프 설계 (🅱)

문서 v1 · 2026-06-22 · 소유 슬롯 🅱(실행·재생성) · 목표 완료일 2026-07-08
관련 문서: `docs/management/structure-and-roles.md`(§12 에이전틱 RAG 어시스턴트), `docs/management/clickme_management_합의문서_v2.1안_2.md`

> **한 줄 요지** — 단일 매니지먼트 어시스턴트(`build_management_agent`) 안에 🅱(실행·재생성) 기능을 붙인다.
> 재생성은 비동기 in-process job으로 돌리고, 후보 선택·승인·실행은 버튼 기반 HITL 경로(REST)로만 처리한다.
> **"LLM은 보여주고, 버튼이 실행한다."**

---

## 0. 배경 / 문제

- 채팅 입구는 이미 하나다 — `api/routers/chat.py`가 매니지먼트 질문을 `build_management_agent`로 라우팅(SSE). 별도 입구를 만들지 않는다. **한 오케스트레이션.**
- 그러나 assistant 그래프(`assistant/graph.py`)는 현재 읽기 툴(reader·budget·before_after·KB)과 `propose_action`(action_type+tier 카드)만 갖는다. **🅱의 실제 기능(재생성 실행·실행 결과 조회)을 그래프 안에서 부르지 않는다.**
- `api/routers/management.py`에는 🅱 기능이 이미 REST로 존재한다(`/regenerate`·select·`/approve_proposal`·`/execute`·`/audit/{approval_id}`). 다만 채팅과는 분리돼 있다.

**목표** — 흩어진 🅱 기능을 assistant 그래프가 부를 수 있는 툴로 묶고, 재생성은 비동기 job으로 실행한다. 단일 입구·기존 승인/실행 경로·A/B import 경계를 모두 유지한다.

---

## 1. 아키텍처와 경계

채팅이 🅱 기능을 부르되 A/B import 경계는 그대로 지킨다. 세 레이어로 나눈다.

```
[assistant 그래프 / 오케스트레이터 레이어]   ← 소유권 보류, A/B 양쪽 contract 사용 허용
   campaign_id 받아서
   → detection(🅰)으로 DiagnosisResult 확보       (contract)
   → 🅱 job 서비스에 DiagnosisResult 넘김          (contract)
         │
         ▼
[🅱 job 서비스 — 보은(B) 소유]               ← contract-in / contract-out, detection import 안 함
   start(diagnosis, context) → job_id          (백그라운드로 rank() 실행)
   get(job_id) → 상태·후보·proposal
   select(job_id, candidate_id) → ActionProposal  (package())
         │
         ▼
[기존 승인 → 실행 경로]                       approval.py(🅰) → executor(🅱) → audit_log(🅱)
```

**경계 원칙**
- 🅱 job 서비스는 **`DiagnosisResult`를 입력으로 받기만** 하고 진단을 생산하지 않는다. detection(🅰) import 금지 불변식을 유지한다(접점은 `contracts`뿐, import-linter 강제).
- "campaign_id → 진단 → 재생성"을 잇는 오케스트레이션은 detection·regeneration 양쪽을 contract로 부를 수 있는 **assistant 툴/라우터 레이어**에 둔다. 이 레이어는 이미 `management.py`가 detection(`run_detection`)·regeneration을 둘 다 부르므로 새 위반이 아니다.
- 보은이 **새로 만드는 것은 가운데 박스(job 서비스 + DB 상태)뿐**이다. 양 끝(진단 확보·승인/실행)은 기존 경로 재사용.

---

## 2. job 서비스 + DB 상태 + 라이프사이클

### 2.1 새 테이블 `regeneration_jobs` (core/models.py — 🤝 공동 변경, Alembic 1회)

| 컬럼 | 내용 |
|---|---|
| `id` | job_id (uuid, pk) |
| `tenant_id` · `campaign_id` | 소유·대상 |
| `status` | QUEUED → RUNNING → {AWAITING_SELECTION / PROPOSED / OBSERVE / CREATIVE_UNAVAILABLE / FAILED} |
| `selection_token` | rank()가 낸 선택 토큰 (nullable) |
| `candidates` | JSON — AWAITING_SELECTION 후보 목록 |
| `selected_candidate_id` | 선택된 후보 id (PROPOSED 시 기록 — select 멱등 판정 근거) |
| `proposal` | JSON — PROPOSED/선택 후 ActionProposal |
| `outcome_reason` · `error` | 관망·실패 사유 |
| `created_at` · `updated_at` · `started_at` · `finished_at` | 타임스탬프 (UTC-aware) |

**인덱스** — `tenant_id` · `campaign_id` · `status` · `created_at`, `selection_token` unique(nullable, Postgres는 NULL 다중 허용).

### 2.2 job 서비스 `RegenerationJobService` (🅱 소유 — `execution/service/` 아래)

- `start(diagnosis, context) -> job_id`
  1. 행 INSERT (QUEUED)
  2. `asyncio.create_task(...)`로 백그라운드 코루틴 시작(채팅 턴보다 오래 살아야 하므로 응답-스코프인 FastAPI `BackgroundTasks` 대신 `create_task`). 코루틴은 자체 `AsyncSessionLocal()`을 연다(요청 세션은 채팅 응답 후 닫힘).
  3. 코루틴: RUNNING(`started_at` 기록) → `agent.rank()` → `RemediationOutcome`을 행 상태로 매핑(§2.4) → `finished_at` 기록.
- `get(job_id) -> JobView` — 행 읽기. **`job.tenant_id == str(org_id)` 검증 필수**(아니면 404).
- `select(job_id, selected_id) -> outcome` — §2.5 절차.

**task 레퍼런스 관리** (GC·예외 누락 방지):

```python
self._tasks: set[asyncio.Task] = set()

task = asyncio.create_task(self._run_job(job_id))
self._tasks.add(task)
task.add_done_callback(self._tasks.discard)
```

- 예외 처리는 **`_run_job` 내부 top-level try/except → 행을 FAILED + error로 업데이트**가 1차(여기서 job_id를 알기 때문). done_callback은 레퍼런스 회수 + 혹시 빠져나온 예외 로깅. **"task만 던지고 끝" 금지.**

### 2.3 v1 한계 (반드시 명시)

> **v1은 in-process async job으로 구현한다.** `uvicorn --workers 1` 전제를 유지하며, 앱 재시작 / 프로세스 분산(multi-worker) / 서버 종료 시 실행 중 job의 완료를 보장하지 않는다. 운영 확장 경로는 SQS/Celery/RQ 같은 외부 큐 + worker로 분리한다.

알려진 실패 모드 4종: ① 앱 재시작 → 실행 중 job 중단 ② 프로세스 2개 이상 → select가 다른 프로세스로 가면 `agent._pending` 없음 ③ 예외 미처리 → task 조용히 사망(§2.2 done_callback로 완화) ④ 서버 종료 → job RUNNING에 멈춤.

**agent 싱글톤 제약 (계약):**

> `RemediationAgent`는 선택 라운드 상태를 `_pending[token]`에 인메모리로 보관한다(코드 주석상 "데모/테스트 전용"). 따라서 rank와 select는 **같은 프로세스의 같은 agent singleton**에서 실행되어야 한다. 이를 위해 v1은 `uvicorn --workers 1`과 in-process job runner를 전제로 한다. 앱 재시작 또는 multi-worker 환경에서는 AWAITING_SELECTION 상태의 job이 선택 불가능해질 수 있다.

이 경우 select는 **409 + `SELECTION_CONTEXT_EXPIRED`**(§2.5 step 5)로 응답한다. 이는 rank 결과가 아니라 select 시점 에러이므로 `contracts`의 `OutcomeReason` enum에 넣지 않고 **job 레이어 응답 코드**로만 둔다. job.status는 `AWAITING_SELECTION` 그대로 유지(상태가 "선택 대기였는데 컨텍스트가 소실됨"을 정직하게 보여줌). FAILED로 덮지 않는다.

### 2.4 RemediationOutcome → job 상태 매핑

| rank 결과 | job 상태 | 저장 |
|---|---|---|
| (rank 시작) | QUEUED → RUNNING | `started_at` |
| creative 후보 있음(AWAITING_SELECTION) | AWAITING_SELECTION | `candidates` + `selection_token` |
| 후보 없이 바로 제안(PROPOSED) | PROPOSED | `proposal` |
| 관망(OBSERVE) | OBSERVE | `outcome_reason` |
| 생성 불가 / 4-3 실패 / creative fallback 불가(CREATIVE_UNAVAILABLE) | CREATIVE_UNAVAILABLE | `outcome_reason` |
| 예외 발생 | FAILED | `error` |

### 2.5 select 절차 (상태 전이 + 프론트 재시도 노출 API)

```
select(job_id, selected_id):
  1. job 조회 (없으면 404)
  2. tenant 검증 (job.tenant_id == org_id, 아니면 404 — 존재 노출 금지)
  3. status 검증:
       AWAITING_SELECTION             → 진행
       PROPOSED & 같은 selected_id     → 저장된 proposal 반환(멱등)
       그 외(다른 selected_id 포함)     → 409
  4. selected_id ∈ job.candidates 검증 (아니면 422)
  5. agent.package(selection_token, tenant_id, selected_id)
       → _pending 없으면 409 SELECTION_CONTEXT_EXPIRED
  6. proposal·selected_candidate_id 저장, status=PROPOSED, finished_at 기록
```

**selected_id 검증 = 이중 방어**(executor 4단계 재검증 철학과 동일 결).
- 1차(job 서비스, step 4): 프론트가 임의 id를 던지면 깔끔하게 422.
- 2차(package 내부): `package()`가 이미 `selection.claim(token, selected_id)`로 `SelectionRound.candidate_ids`와 대조(`regeneration.py`). service를 우회해도 막힌다.
- 1차의 목적은 보안이 아니라 **응답 품질** — 2차만 있으면 `ValueError→INPUT_INVALID`로 뭉뚱그려진다.

**멱등 근거 문장** — select는 상태 전이이면서 동시에 프론트 재시도에 노출되는 API라서, **같은 선택은 멱등하게 받아주고, 다른 선택은 409로 막는 것**이 가장 안정적이다.

---

## 3. assistant 툴 + 채팅 UX

assistant 그래프(`@tool`)에 🅱 기능을 부르는 툴을 추가한다. **툴 바디는 전부 🅱 소유 코드**, 그래프 등록 줄만 소유권 보류(§5).

### 3.1 추가 툴 4종

| 툴 | 시그니처 | 하는 일 |
|---|---|---|
| `start_regeneration` | `(campaign_id, risk_appetite="conservative")` | 오케스트레이터가 detection으로 진단 확보 → job 서비스 `start()` → `{job_id, status:"queued"}` 즉답 |
| `check_regeneration` | `(job_id)` | job 서비스 `get()` → 상태 + (AWAITING_SELECTION이면 후보 목록) |
| `execution_history` | `(campaign_id)` | 그 캠페인에 실행된 액션 이력 요약(audit_log 읽기, org 스코프) |
| `get_audit` | `(approval_id)` | 단일 승인-실행 감사 상세(기존 `/audit/{approval_id}` 재사용, org 스코프) |

**`start_regeneration` 호출 가드** — 재생성은 무거운 비동기 job(이미지 생성·시뮬)이다. **사용자가 개선/재생성 의도를 명확히 표현했을 때만** 호출한다("개선/시안/바꿔" 등). 단순 현황·진단 질문에는 read 툴만 쓴다. 이 가드는 그래프 시스템 프롬프트 + 툴 description에 명시한다.

### 3.2 채팅 UX 흐름 (비동기 → 멀티턴 polling)

```
사용자: "이 캠페인 왜 부진해, 개선안 보여줘"
 → LLM이 live_campaign_detail로 진단 맥락 설명
 → (개선 의도 명확) start_regeneration 호출
 → "개선 시안 생성 시작했어요. job_id=xxx, 보통 N초 걸려요"
   (응답 즉시 반환 — 무거운 생성은 백그라운드)

사용자: "됐어?"  (또는 프론트가 job_id로 폴링)
 → check_regeneration(xxx)
   - RUNNING                 → "아직 생성 중이에요"
   - AWAITING_SELECTION      → 후보 3개 카드(copy·미리보기·근거) 표시
   - OBSERVE/CREATIVE_UNAVAILABLE → 사유 설명
```

### 3.3 핵심 결정

1. **선택·승인은 채팅 자유발화로 받지 않는다.** 후보 선택(`select`)·제안 승인은 **구조화 UI(카드 버튼)** 로만 받는다. LLM이 "1번 골라줘"를 파싱해 select를 호출하면 정보 방화벽·오발주 위험. 채팅은 후보를 **보여주기만** 하고, 선택 클릭 → `/select`(또는 job 서비스 select) → 승인 카드 → `/approve`·`/execute`. 합의문서 §3 "오케스트레이터=입, 실행은 승인 경로" 원칙과 정합.
2. **폴링 우선.** v1은 프론트 폴링(job_id로 `check_regeneration` 또는 REST `/regenerate/jobs/{id}`). SSE 잡 완료 푸시는 후순위.
3. **detection 호출 위치** — `start_regeneration` 툴 바디(오케스트레이터 레이어)에서 detection을 호출해 진단을 만들고, job 서비스엔 완성된 `DiagnosisResult`만 넘긴다(§1 경계 일관).

> **v1 채팅 UX 정본** — LLM이 개선 작업을 시작하고 상태를 설명하지만, 후보 선택과 승인은 버튼 기반 HITL 경로로만 처리하는 비동기 polling 구조.

---

## 4. 실행 트리거(HITL) 단일화 + 감사 조회

### 4.1 HITL 경로 단일화 — REST·버튼

현재 행동 실행 트리거가 두 군데 있다.
- **(가) assistant 그래프 내부** `propose_action` → `requires_approval`이면 `interrupt()`로 멈춤 → `thread_id` 반환(LangGraph checkpointer 재개).
- **(나) REST 경로** `/regenerate`→`/select`→`/approve_proposal`→`/execute`. job 서비스도 (나)로 수렴.

**v1 결정 — 실행은 (나) REST·버튼 경로로 단일화.** 채팅의 `propose_action`/`interrupt`(가)는 **"제안 카드 표시"까지만** 쓰고, 실제 승인·실행은 (나)로.
- §3에서 "승인은 자유발화 금지, 버튼 HITL"로 닫음 → 버튼은 REST를 부르는 게 자연스럽다.
- (가)의 interrupt 재개는 checkpointer 영속성에 묶여 §2의 "in-process·재시작 시 미보장" 한계를 또 안는다. 영속 안 되는 재개 경로를 둘이나 들 이유가 없다.
- → **`propose_action`은 카드만, 승인/실행 트리거는 `/approve`·`/execute` 버튼.** thread_id 기반 재개는 v1 비활성(후순위).

> **정본** — v1에서는 "LLM 그래프가 실행을 재개하는 구조"를 버리고, "LLM은 보여주고 버튼이 실행한다"로 단일화한다.

### 4.2 실행 결과·감사 조회 (읽기 — 채팅이 답해야 할 빈칸)

| 툴/엔드포인트 | 내용 |
|---|---|
| `execution_history(campaign_id)` | 그 캠페인의 실행 이력 요약 — audit_log에서 action_type·status·시각·approval_id 목록 |
| `get_audit(approval_id)` | 단일 승인→실행 감사 상세(기존 `/audit/{approval_id}` 재사용, 신규 아님) |

- `execution_history`는 신규지만 **읽기 전용이고 🅱 `audit_log` 위에 얹는 것**이라 경계가 깔끔하다.
- **두 조회 모두 인증·소유권 필수** — `org_id` 스코프로 필터링하고, 타 테넌트 audit은 보이지 않게(존재 노출 금지, 404). §2 job 테넌트 검증과 같은 규칙.

---

## 5. 소유권 조율 지점 + 테스트 + 스코프

### 5.1 소유권 조율 지점 (설계 확정, "누가 수정"은 보류 — 합의 필요 목록)

| 파일 | 변경 | 조율 |
|---|---|---|
| `core/models.py` | `regeneration_jobs` 테이블 + Alembic | 🤝 공동 (DB 스키마 = 계약) |
| `execution/service/` 신규 job 서비스 | `RegenerationJobService` | 🅱 단독 |
| `execution/` audit 읽기 헬퍼 | `execution_history` 바디 | 🅱 단독 |
| `assistant/tools.py`·`graph.py` | 툴 4종 등록 + 시스템 프롬프트 가드 | 🅰 소유 파일 → **등록은 🅰 합의**(또는 assistant 공동화 재논의) |
| `api/routers/management.py` | `/regenerate/jobs/{id}`·select job 엔드포인트 (**인증·소유권 검증 포함**) | 🤝 얇은 라우터 |
| `core/config.py` | (필요 시) job 타임아웃 등 setting | 🤝 |

핵심 — **무거운 로직은 전부 🅱 소유 파일**, 🅰 파일엔 **툴 등록 줄 + description**만 들어간다. 그 한 줄을 🅰와 합의(또는 assistant 공동화)하면 끝.

### 5.2 테스트 (TDD — 검증 가능한 성공 기준)

- **job 라이프사이클**: start→RUNNING→AWAITING_SELECTION 전이, OBSERVE/CREATIVE_UNAVAILABLE/FAILED 매핑(RemediationOutcome 5종 → 행 상태).
- **select 멱등**: 같은 selected_id 재시도 → 같은 proposal / 다른 selected_id → 409 / 후보 밖 id → 422.
- **테넌트 격리**: 타 org의 job get·select → 404, audit·execution_history 조회 → 404. **start/check 권한 검증 포함.**
- **`_pending` 소실**: AWAITING_SELECTION인데 `_pending` 없음 → 409 `SELECTION_CONTEXT_EXPIRED`, job.status는 AWAITING_SELECTION 유지.
- **task 예외 → FAILED**: rank()가 예외를 던져도 task가 조용히 죽지 않고 행이 FAILED + error로 갱신.
- **폴백(키 없음)**: assistant 폴백 모드에서도 read 툴은 동작(게이트 #9 재현성).

### 5.3 v1 스코프 — 명시적 제외 (Won't)

- 운영급 job 큐(SQS/Celery/RQ), 멀티워커, job 재시작 복구.
- **agent `_pending` 선택 컨텍스트 영속화**(후보를 job 행에 저장해 package 재구성하는 강화 경로).
- SSE job 완료 푸시(폴링으로 대체).
- LangGraph interrupt 재개 경로.
- 채팅 자유발화로 선택·승인.

---

> 섹션 1~5 모두 합의 완료. 다음 단계 — `writing-plans`로 구현 계획을 작성한다.
