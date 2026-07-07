# 채팅 어시스턴트 · 오케스트레이터 스펙 — 업계 표준안 (참고용 B)

> 📌 **귀결 (역사 문서)** — 최종 구현은 본 문서 §0의 패턴 ②(single tool-calling
> agent)에 해당한다. 통합 딥에이전트(deepagents `create_deep_agent` + CHAT_POLICY,
> 도메인 위임은 @tool, deepagents 고유 서브에이전트 기능 미사용). Supervisor(패턴 ①)의
> 상위/하위 분리 대신 단일 에이전트 + 도구 계층으로 단순화. 현행은
> chat-deep-agent-orchestrator.context-notes.md 참고.
>
> 이 문서는 [chat-orchestrator-spec.md](./chat-orchestrator-spec.md)의 **결정 항목을 "가장 보편적인 방법(업계 표준)"으로 채운 사본**이다(참고용).
> 우리 프로젝트에 실제 채택하는 사본은 [chat-orchestrator-spec.our-fit.md](./chat-orchestrator-spec.our-fit.md).
> 질문(§3 체크리스트)은 원본 그대로 두고, 각 `결정:` 칸만 "표준이라면 이렇게"로 채웠다.

**한 줄 요약** — 멀티역량 챗 어시스턴트의 업계 정석은 **Supervisor/Router 패턴**이다. 상위 LLM(supervisor)이 분류·위임하고, 하위는 tool-calling 서브에이전트. 우리 스택(LangGraph)이면 **LangGraph Supervisor + checkpointer 스레드 영속 + LangSmith threads**가 표준 답이다.

---

## 0. 멀티역량 챗의 보편 패턴 3가지

| 패턴 | 설명 | 대표 구현 | 적합 규모 |
|---|---|---|---|
| **① Router/Supervisor** | 상위 LLM이 분류·디스패치, 하위는 전문 서브에이전트 | LangGraph `supervisor`, Anthropic orchestrator-workers | **중·대규모, 도메인 경계 뚜렷할 때** |
| **② Single tool-calling agent** | 에이전트 1개 + 모든 역량을 function/tool로 | LangGraph `create_react_agent`, OpenAI function calling | 소규모·역량 적을 때, 시작 빠름 |
| **③ Handoff 멀티에이전트** | 에이전트끼리 제어권을 넘김 | OpenAI Agents SDK(Swarm), CrewAI, AutoGen | 복잡한 협업·동적 위임 |

**업계 디폴트는 ①.** 우리가 이미 LangGraph를 쓰므로 "정석대로"면 **LangGraph Supervisor**. 공통 계약 = tool/function 스키마, 상태 = checkpointer thread, 추적 = LangSmith threads(`session_id`를 thread_id로).

> 우리 적합안(문서 A)은 ①의 **경량판** — supervisor를 LLM 에이전트가 아니라 **결정론 분류기 1콜 + dict 디스패치**로 단순화한 것. 본 문서 B는 그 단순화를 걷어낸 **정석 ①** 버전이다.

---

## 1. 목표 (Goals)

- **G1. 단일 진입점** — 사용자는 하나의 채팅에서 생성·시뮬·관리·일반조언·불러오기를 한다.
- **G2. 전수 추적** — 모든 LLM 호출/응답이 LangSmith에 남는다(누락 0). 한 대화의 턴들이 스레드로 묶인다.
- **G3. 도메인 독립성** — 각 도메인은 내부 구현을 자유롭게, 단 **공통 계약(tool 스키마)** 을 지킨다.
- **G4. 비파괴 연결** — 기존 도메인 파이프라인 위에 supervisor 그래프만 얹는다.
- **G5. 예측가능·테스트가능** — 표준에서는 라우팅도 LLM이지만, 평가 데이터셋·LLM-judge로 예측가능성을 확보한다.

### 비목표 (Non-goals, 이번 범위 아님)
- (표준에서는 비목표 완화) 채팅 DB 영속화는 오히려 **표준 채택**(checkpointer 스레드).
- 완전 자율 단일 ReAct(②)는 도메인 3개 규모엔 비표준 → supervisor(①) 권장.

---

## 2. 제안 아키텍처 (업계 표준 — LangGraph Supervisor)

```
프론트(단일 채팅, session_id 보유)
  └─ POST /api/assistant/chat  (표준 단일 진입점 신설)
       └─ Supervisor Graph  (1턴 = 1 트레이스 루트 · checkpointer 영속)
            ├─ supervisor(LLM)            라우팅·위임도 LLM이 결정
            ├─ handoff(Command) → 서브에이전트 (tool-calling)
            │     ├─ 생성  : create_react_agent + start_generation 도구
            │     ├─ 시뮬  : create_react_agent + start_simulation 도구
            │     └─ 관리  : 에이전틱 RAG (이미 ReAct)
            └─ 서브에이전트 → supervisor 제어 반환(Command)  ← 멀티의도 순차
       (전체 astream_events로 토큰·진행 스트리밍)
```

- **공통(Common)** = supervisor 그래프 + tool/handoff 스키마 + checkpointer + LangSmith threads.
- **도메인(Domain)** = 각 서브에이전트(create_react_agent). 표준은 전부 자율 루프.

---

## 3. 정해야 할 것 (Decision Checklist) — 업계 표준 결정

### A. 오케스트레이션
- [x] **A1. 최상위 라우팅 방식** — `결정: (a) 의도분류 + 서브에이전트, 단 supervisor를 LLM 에이전트로(LangGraph Supervisor).` 라우팅도 LLM.
- [x] **A2. 의도 카테고리 집합** — `결정: generate/simulate/manage/retrieve/advise를 handoff 도구 스키마로 정의.`
- [x] **A3. 멀티 의도 처리** — `결정: supervisor가 순차 위임(LLM 자율). 서브에이전트가 Command로 제어 반환.`
- [x] **A4. 엔드포인트·소유** — `결정: /api/assistant/chat 신설(표준 단일 진입점). 공통부 팀 소유.`

### B. 도메인 서브에이전트 **공통 계약 (가장 중요 — seam)**
- [x] **B1. 입력 계약** — `결정: 표준 messages 상태(LangGraph MessagesState) + 도구 인자 스키마.`
- [x] **B2. 출력 계약** — `결정: AIMessage/ToolMessage + Command(goto, update). 잡 시작은 도구 결과로 started_event.`
- [x] **B3. 트리거·핸드오프 이벤트** — `결정: started_event {event, job_id, stream_url, domain} 동일, astream_events로 통합 전달.`
- [x] **B4. 등록 방식** — `결정: supervisor 노드 + 서브에이전트 노드 그래프 등록(handoff 도구).`

### C. 상태 / 세션
- [x] **C1. 대화 상태 보관처** — `결정: 서버 세션 + checkpointer 영속(표준은 스레드 영속).`
- [x] **C2. session_id 발급 주체** — `결정: 서버 발급. thread_id로 직결.`
- [x] **C3. 슬롯 누적 방식** — `결정: checkpointer state에 누적(매 턴 재추출 X).`

### D. LangSmith 추적 (필수 — G2)
- [x] **D1. 계측 규칙** — `결정: raw SDK 금지, LangChain/@traceable 전수. (raw genai 전면 제거)`
- [x] **D2. 트레이스 루트** — `결정: 1턴 = 1 루트 run assistant.chat.turn, 그래프 하위 자동 중첩.`
- [x] **D3. 스레드 상관키** — `결정: LangSmith threads — session_id = thread_id로 모든 run 묶음.`
- [x] **D4. 프로젝트/네이밍** — `결정: LANGCHAIN_PROJECT=clickme. supervisor.* / <domain>.* 네이밍.`
- [x] **D5. 비용 가시화** — `결정: usage 수동 부착 + 가격표 설정(표준 운영).`
- [x] **D6. 평가(eval)** — `결정: dataset + LLM-judge 정식 도입(라우팅 정확도·답변 품질).` 표준은 평가로 예측가능성 확보.

### E. RAG
- [x] **E1. 코퍼스 소유·분담** — `결정: 공용 코퍼스 + 도메인 전용 혼합, 소유 명시.`
- [x] **E2. 공용 vs 도메인 전용** — `결정: 공용 retrieve 도구 + 도메인별 RAG 병행(표준).`
- [x] **E3. 벡터 스토어·스키마** — `결정: pgvector documents/embeddings 단일 합의 + Alembic(단독 PR).`
- [x] **E4. 임베딩 모델** — `결정: 모델/차원(1536) 통일.`

### F. 핸드오프 / 스트리밍
- [x] **F1. 잡 진행률 전달** — `결정: astream_events 표준 스트리밍 + 도메인 SSE 재사용.`
- [x] **F2. 동기 vs 비동기** — `결정: 조회 즉답, 생성/시뮬은 백그라운드 잡 + 스트림 구독.`

### G. 프론트
- [x] **G1. UI** — `결정: 단일 챗 UI + 도메인별 진행률 카드(표준).`
- [x] **G2. 결과 표현** — `결정: 인라인 진행률/카드 + 상세 페이지 링크.`

### H. 협업 / 경계 (DDD)
- [x] **H1. 서비스 공개 API** — `결정: 각 도메인 진입점을 handoff 도구로 래핑, 내부 import 금지.`
- [x] **H2. 공통부 변경 절차** — `결정: api/main.py append-only, DB 스키마 단독 PR + 사전공지.`
- [x] **H3. 통합 시점·테스트** — `결정: 서브에이전트 독립 개발 → supervisor 합류 → 통합 테스트.`

---

## 4. 기능별 방향 가이드 (표준 채택 시)

| 기능 | 현 상황 | 표준 방향 | 비고 |
|---|---|---|---|
| **생성** | LangGraph 5단계 파이프라인(추적됨) | `create_react_agent` + start_generation 도구 | 자율 루프 |
| **시뮬** | `SimulationService.start` + SSE | `create_react_agent` + start_simulation 도구 | project_id 필요 |
| **관리** | 에이전틱 RAG 구현 완료 | supervisor에 서브그래프로 합류 | 이미 표준형 |
| **불러오기** | 내역 DB 조회 | 공용 retrieve 도구 | 권한 필터 |
| **일반조언** | CLIO(raw Gemini, 미추적) | LangChain LLM 노드로 계측 | D1 |

> 공통 원칙: **각 서브에이전트는 tool/handoff 계약·LangSmith threads만 지키면 내부 자유.**

---

## 5. 미해결 / 리스크

- 표준 supervisor는 라우팅도 LLM이라 **비용·지연·비결정성↑** → D6 평가 데이터셋으로 회귀 방지 필수.
- checkpointer 영속 도입 시 **DB 스키마·마이그레이션 부담**(공통부 단독 PR).
- 멀티에이전트 handoff 디버깅 난이도 → LangSmith threads로 상관.
- 이미지 모델 비용 0 표기(토큰 비기반) → usage 수동 부착.

---

## 6. 다음 단계 (표준 채택 시)

1. supervisor 그래프 + handoff 도구 스키마 단독 PR.
2. checkpointer/threads(C·D) 인프라 합의 + Alembic.
3. 서브에이전트(create_react_agent) 독립 개발 → supervisor 합류 → eval 데이터셋.

---

## 7. 부록 — 루프 엔지니어링 (일반 설명)

**루프 엔지니어링** = 에이전트의 핵심 제어 루프(모델 → 도구 → 관측 → 반복 → 종료)를 안전·예측가능하게 설계하는 규율. "에이전트 = 모델이 도구를 들고 루프를 도는 것"이라는 정의에서, 그 루프 자체를 다루는 일이다. 프롬프트 엔지니어링이 "한 번의 입력"이라면, 루프 엔지니어링은 "여러 번의 호출이 이어지는 방식"을 다룬다.

다루는 항목 — ① 종료 조건 ② 반복 예산(budget, 폭주·비용 방지) ③ 관측 피드백 ④ 상태 누적 ⑤ 중단·인계(HITL) ⑥ 컨텍스트 관리(긴 루프의 히스토리 압축).

루프 종류 — **자율 루프(LLM이 반복·종료 결정, ReAct)** vs **결정론 루프(코드가 결정, slot-filling/상태머신)**.

**표준 패턴(① supervisor)에서는** supervisor 자체가 자율 루프(어느 서브에이전트로 갈지, 언제 끝낼지 LLM이 판단)이고 각 서브에이전트도 `create_react_agent` 자율 루프다. 즉 표준은 **루프가 모든 계층에 있다.** 유연하지만 예측가능성은 평가(D6)·반복 상한·thread 추적으로 확보한다.

> 비교 — 우리 적합안(문서 A)은 **최상위 루프를 제거**(결정론 분류 1콜)하고 루프를 서브에이전트 안에만 둔다. 후순위·소규모 기능에 더 맞는 트레이드오프. 채팅이 핵심으로 승격되고 동적 위임이 필요해지면, 공통 계약을 지킨 채 분류기 자리만 본 문서 B의 supervisor로 교체하면 된다.
