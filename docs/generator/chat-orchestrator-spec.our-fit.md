# 채팅 어시스턴트 · 오케스트레이터 스펙 — 우리 프로젝트 적합안 (확정본 A)

> 이 문서는 [chat-orchestrator-spec.md](./chat-orchestrator-spec.md)의 **결정 항목을 "우리 프로젝트(ClickMe)에 가장 맞는 방식"으로 채운 사본**이다.
> 같은 사안을 "업계 표준(참고용)"으로 채운 사본은 [chat-orchestrator-spec.industry-standard.md](./chat-orchestrator-spec.industry-standard.md).
> 질문(§3 체크리스트)은 원본 그대로 두고, 각 `결정:` 칸만 채웠다.

**한 줄 요약** — 최상위는 **얇은 결정론 오케스트레이터**(의도분류 1콜 → 디스패치, 루프 없음). 깊은 루프는 서브에이전트 안에만 둔다. 기존 도메인 진입점·SSE를 그대로 재사용하고(비파괴), management의 `AskRequest/AskResult`를 공통 계약 템플릿으로 승격한다.

---

## 0. 현 코드 기준 사실 확인 (권장의 근거)

원본 §4 표는 일부 현실과 어긋나 있어 먼저 바로잡는다.

1. **오케스트레이터의 "최소 버전"이 이미 돈다.** [chat.py:46-87](../../backend/api/routers/chat.py)이 키워드 매칭으로 management 질문만 [build_management_agent](../../backend/domain/management/assistant/agent.py)로 보내고, 나머지는 CLIO(raw Gemini)로 흘린다. → "신설"이 아니라 **이걸 진화**시키는 문제다.
2. **공통 계약(B)의 템플릿이 이미 있다.** management의 [`AskRequest → AskResult`](../../backend/domain/management/assistant/contracts.py)(`answer/citations/used_tools/suggested_action/requires_approval/thread_id`). 진입점도 단일 함수, LangSmith `run_name/tags/metadata`까지 붙어 있다. → **새 계약 발명 불필요, 일반화만.**
3. **"생성 슬롯형 PoC 존재"는 사실이 아니다.** [generator/chat/](../../backend/domain/generator/chat/)는 비어 있다. 그리고 **추적 누락(G2 위반)의 유일한 실범인은 CLIO** — raw `google.generativeai` 직접 호출이라 LangSmith에 안 잡힌다. 나머지(생성 파이프라인·관리·시뮬)는 추적된다.

---

## 1. 목표 (Goals)

- **G1. 단일 진입점** — 사용자는 하나의 채팅에서 생성·시뮬·관리·일반조언·불러오기를 한다.
- **G2. 전수 추적** — 모든 LLM 호출/응답이 LangSmith에 남는다(누락 0). 한 대화의 턴들이 스레드로 묶인다.
- **G3. 도메인 독립성** — 각 도메인은 내부 구현(슬롯형/에이전틱 RAG 등)을 자유롭게, 단 **공통 계약**을 지킨다.
- **G4. 비파괴 연결** — 기존 도메인 파이프라인 코드를 바꾸지 않고 그 위에 오케스트레이터만 얹는다.
- **G5. 예측가능·테스트가능** — 최상위 라우팅은 결정론, 깊은 추론은 도메인 안에서.

### 비목표 (Non-goals, 이번 범위 아님)
- 채팅 대화 자체의 DB 영속화(로컬/무상태 유지) — 합의 시 변경 가능.
- 완전 자율 단일 ReAct(모든 툴을 한 에이전트가) — 추적·제어 난이도로 **보류**.

---

## 2. 제안 아키텍처 (확정 — 우리 적합안)

```
프론트(단일 채팅, session_id 보유)
  └─ POST /api/chat/complete  (기존 엔드포인트 확장 · 신설 X)
       └─ [공통] Orchestrator  (1턴 = 1 트레이스 루트 · 결정론 · 루프 없음)
            ├─ classify_intent           (계측 LLM 1콜)
            ├─ route(dict 레지스트리) → 도메인 서브에이전트 (공통 계약 준수)
            │     ├─ 생성  : 슬롯형(결정론 루프)        → start_generation 트리거
            │     ├─ 시뮬  : 슬롯형(결정론 루프, 경량)  → SimulationService.start 트리거
            │     └─ 관리  : 에이전틱 RAG (구현됨, 자율 루프) → 합류
            ├─ retrieve(불러오기)         (도메인 read · 동기)
            └─ advise(일반 조언)          (계측 LLM · CLIO 추적 전환)
```

- **공통(Common)** = 오케스트레이터(결정론 분류·디스패치) + 공통 계약 + 추적/세션 규약 + 핸드오프 이벤트.
- **도메인(Domain)** = 서브에이전트 내부. 루프는 **여기에만** 산다(§7 참조).

---

## 3. 정해야 할 것 (Decision Checklist) — 우리 적합안 결정

### A. 오케스트레이션
- [x] **A1. 최상위 라우팅 방식** — `결정: (a) 의도분류 LLM 1콜 + 도메인 서브에이전트.` 단일 ReAct(b) 보류. 최상위는 결정론·단일 패스(루프 없음) → G5.
- [x] **A2. 의도 카테고리 집합** — `결정: generate / simulate / manage / retrieve / advise 5개로 고정.` 도메인 경계와 1:1, 분류기 테스트 쉬움.
- [x] **A3. 멀티 의도 처리** — `결정: 턴당 1의도. 애매하면 되묻기(clarify).` 순차 멀티의도는 후순위(지금 안 만듦).
- [x] **A4. 엔드포인트·소유** — `결정: 기존 /api/chat/complete 확장(신설 X). 소유는 공통부 1인, include_router는 append-only.` SSE 배관·stopgap 재사용.

### B. 도메인 서브에이전트 **공통 계약 (가장 중요 — seam)**
- [x] **B1. 입력 계약** — `결정: management AskRequest를 일반화한 SubagentRequest = {messages(history), slots, session_id, project_id, user}.`
- [x] **B2. 출력 계약** — `결정: SubagentResult = action(ask|trigger|answer) · message · started_event(job 시작 시).` (AskResult 확장)
- [x] **B3. 트리거·핸드오프 이벤트** — `결정: started_event = {event, job_id, stream_url, domain}.` 생성은 job_id=generation_id, stream_url=/api/generator/generations/{id}/stream.
- [x] **B4. 등록 방식** — `결정: dict 레지스트리 {intent: handler} + wiring 주입.` chat.py의 if-분기를 레지스트리 lookup으로 교체.

### C. 상태 / 세션
- [x] **C1. 대화 상태 보관처** — `결정: 프론트 무상태(매 턴 히스토리 재전송).` 비목표(DB 영속화 제외)와 정합.
- [x] **C2. session_id 발급 주체** — `결정: 프론트 발급. LangSmith thread 상관키로만 사용.`
- [x] **C3. 슬롯 누적 방식** — `결정: 매 턴 히스토리에서 재추출(stateless).` 누적 저장 X.

### D. LangSmith 추적 (필수 — G2)
- [x] **D1. 계측 규칙** — `결정: raw SDK 직접 호출 금지. CLIO를 langchain_google_genai로 교체.` → 유일한 추적 구멍을 막는 단 하나의 실작업.
- [x] **D2. 트레이스 루트** — `결정: 1턴 = 1 루트 run assistant.chat.turn, 하위 자동 중첩.`
- [x] **D3. 스레드 상관키** — `결정: 모든 run 메타에 session_id(+user_id, project_id). 백그라운드 잡(생성/시뮬)에도 동일 주입.`
- [x] **D4. 프로젝트/네이밍** — `결정: LANGCHAIN_PROJECT=clickme. 네이밍 assistant.* / generator.* / management.*.`
- [x] **D5. 비용 가시화** — `결정: 이미지 모델 per-run 비용 수동 부착.` 생성 파이프라인은 이미 적용(직전 커밋).
- [x] **D6. 평가(eval)** — `결정: 후순위.` 채팅 후순위라 분류기 스모크 테스트만, dataset/judge는 보류.

### E. RAG
- [x] **E1. 코퍼스 소유·분담** — `결정: 관리(에이전틱 RAG)가 KB 소유(정책·플레이북·KPI규칙, 이미 적재). 생성/시뮬은 RAG 미사용(슬롯형).`
- [x] **E2. 공용 vs 도메인 전용** — `결정: 도메인 RAG는 관리만. 공용 retrieve는 도메인 read 요약(벡터 X).`
- [x] **E3. 벡터 스토어·스키마** — `결정: pgvector documents/embeddings는 관리가 이미 사용. 생성 연결엔 신규 스키마 불필요.`
- [x] **E4. 임베딩 모델** — `결정: 1536 통일(기존 유지).`

### F. 핸드오프 / 스트리밍
- [x] **F1. 잡 진행률 전달** — `결정: 도메인 SSE 재사용. 채팅은 started_event만 내보내고 프론트가 도메인 stream_url 구독.`
- [x] **F2. 동기 vs 비동기** — `결정: 즉답(retrieve/advise) 동기, 잡(generate/simulate) 비동기 백그라운드.`

### G. 프론트
- [x] **G1. UI** — `결정: 기존 /chat 단일 재사용 + 도메인별 진행률 카드.`
- [x] **G2. 결과 표현** — `결정: 인라인 진행률/카드(채팅 안), 상세는 결과 페이지 링크.`

### H. 협업 / 경계 (DDD)
- [x] **H1. 서비스 공개 API** — `결정: generator_service.start_generation(req, created_by)→id · stream_events(id) 재사용. 내부 import 금지, 진입점만.`
- [x] **H2. 공통부 변경 절차** — `결정: api/main.py append-only, DB 스키마 단독 PR + 사전공지.`
- [x] **H3. 통합 시점·테스트** — `결정: 생성 먼저 연결 → 시뮬 → 관리 합류. 단계별 통합 테스트.`

---

## 4. 기능별 방향 가이드 (현 구현 기준 — 정정 반영)

| 기능 | 현 상황(정정) | 우리 적합 방향 | 비고 |
|---|---|---|---|
| **생성** | LangGraph 5단계 파이프라인(추적됨). **챗 슬롯형 PoC 없음(빈 디렉터리)** | **슬롯형(결정론 루프) 서브에이전트** → 슬롯 수집 후 `start_generation` 트리거 | 슬롯 추출 LLM만 **계측**(D1) |
| **시뮬** | `SimulationService.start` + SSE 존재 | 슬롯형 경량 — 타깃·표본 수집 후 트리거 | project_id 필요(저장 전제) |
| **관리** | 에이전틱 RAG **구현 완료**(자율 루프·HITL·LangSmith) | 공통 계약으로 합류만 | 손대지 말 것 |
| **불러오기** | 생성/시뮬 내역 DB 조회 가능 | 공용 retrieve(도메인 read 요약 + 상세 링크) | 권한 필터 준수 |
| **일반조언** | **CLIO(raw Gemini, 미추적)** | langchain_google_genai로 **계측 전환** | D1 — 유일한 추적 구멍 |

> 공통 원칙: **각 도메인 서브에이전트는 내부 자유, 공통 계약(B)·추적(D)·핸드오프(F)만 지킨다.**

---

## 5. 미해결 / 리스크

- 백그라운드 잡(생성/시뮬)은 비동기 분리라 **완전 중첩 트레이스가 어려움** → `session_id` 스레드로 상관(완전 부모-자식 대신).
- 도메인별 루프 종류 상이(결정론 슬롯형 vs 자율 RAG) → **공통 계약(B) 미합의 시 합류 실패**. 계약 먼저.
- 이미지 모델 비용이 LangSmith에 0으로 보일 수 있음(토큰 비기반) → D5 수동 부착.
- 채팅 무상태 유지 시 멀티턴 슬롯/맥락 한계 → C 항목 결정으로 수용(매 턴 재추출).

---

## 6. 다음 단계 (우리 적합안)

1. **B 공통 계약 스켈레톤**(`SubagentRequest/Result` + 레지스트리)을 단독 PR로 먼저 머지.
2. **생성 서브에이전트(슬롯형)** 구현 → chat.py 레지스트리에 등록 → `start_generation` 트리거.
3. CLIO 계측 전환(D1) → 시뮬 슬롯형 → 관리 합류 순.

---

## 7. 부록 — 루프 엔지니어링 관점 (이 적합안에 적용)

**루프 엔지니어링** = 에이전트의 핵심 제어 루프(모델 → 도구 → 관측 → 반복 → 종료)를 안전·예측가능하게 설계하는 규율. 다루는 항목은 ① 종료 조건 ② 반복 예산(budget) ③ 관측 피드백 ④ 상태 누적 ⑤ 중단·인계(HITL) ⑥ 컨텍스트 관리.

루프에는 두 종류가 있다.

| | 자율 루프 (agentic/ReAct) | 결정론 루프 (slot-filling/상태머신) |
|---|---|---|
| 반복·종료 결정 | **LLM이 스스로** | **코드가** (필수 값 다 찼나?) |
| LLM 역할 | 계획·도구선택·종료판단 전부 | 추출만 |
| 예측가능성 | 낮음(유연·폭주위험) | 높음(테스트 쉬움) |
| 우리 예 | **관리** | **생성·시뮬** |

**핵심 — 루프는 "오케스트레이터에 도입"하는 게 아니라 "서브에이전트 안에 가둔다".**

| 계층 | 루프 종류 | 종료 조건 |
|---|---|---|
| 오케스트레이터 | **없음(단일 패스)** | 1콜 분류 후 즉시 디스패치 |
| 생성·시뮬 서브에이전트 | 결정론 슬롯필링 루프 | 필수 슬롯 충족 → 트리거 |
| 관리 서브에이전트 | 자율 ReAct 루프(구현됨) | 도구 호출 없음 or `_MAX_ROUNDS`(=5) |

관리의 [graph.py](../../backend/domain/management/assistant/graph.py)가 이미 잘 엔지니어링된 자율 루프다 — `agent→tools→agent` 순환, 종료 2조건(도구 없음/라운드 상한), 상태 누적(`used_tools·live_evidence·tool_rounds`), HITL `interrupt`. 생성·시뮬은 이보다 가벼운 **결정론 루프**로 같은 자리에 넣는다. 최상위에 자율 루프를 얹으면 그게 보류한 단일 ReAct(A1-b)이고 G5와 충돌한다.
