# 오케스트레이션 챗봇 아키텍처 (4-4)

> 시뮬레이션(4-1)·제너레이터(4-3)·매니지먼트(4-2)를 하나의 채팅으로 묶는 **오케스트레이터(조율자)** 설계와 작업 우선순위.
> 선행 설계 [chat-management-agentic-rag spec](../superpowers/specs/2026-06-21-chat-management-agentic-rag.md)의 "범위 밖(후속)" 항목을 실행 계획으로 구체화한다.

작성 2026-06-23 · 상태 제안(핵심 결정 일부 확정 — LLM·호출방식·루프정책) · 기능 4-4(후순위, 핵심 3기능 완료 후 착수)

---

## 1. 목적과 범위

자유 질문에 답하면서, 필요하면 **시뮬레이션을 돌리고 / 광고 시안을 생성하고 / 매니지먼트 성과를 조회·제안**까지 한 창구에서 처리하는 채팅을 만든다. 목표는 "사람과 똑같은 대화"가 아니라 **세 도메인을 오가는 번거로움을 없애고, 실행 결과를 대화 맥락에 끼워 보여주는 것**.

- **포함** — 오케스트레이터 본체, 3개 도메인 서브에이전트 연결, 플로팅 챗봇 UI, 채팅 내 기능 실행 위젯, 세션·내역 영속화(프로젝트 귀속).
- **제외(후속)** — 음성·멀티모달 입력, 자동 실행(사람 승인 없는 집행), 예측 보정(calibration).

---

## 2. 현재 상태 (as-is)

이미 깔려 있는 자산이 많아, 본 작업은 대부분 **연결과 셸**이다.

| 영역 | 현황 | 위치 |
| --- | --- | --- |
| 매니지먼트 서브에이전트 | **완성**. LangGraph ReAct + 하이브리드 RAG(실측 live + pgvector KB) + HITL interrupt. `build_management_agent(settings)→ask→AskResult` | `backend/domain/management/assistant/` |
| 채팅 라우터 | `POST /api/chat/complete` SSE. **통합 딥에이전트**(`build_unified_chat_agent`, OpenAI gpt-4.1)가 LLM 판단으로 3개 도메인에 tool 위임(2026-06-30 키워드 라우팅→통합 에이전트로 전환 완료, 8장 참고) | `backend/api/assistant/deep_agent_builder.py`·`backend/api/routers/chat.py` |
| 시뮬/제너 서브에이전트 | **없음**. 서비스 실행 진입점만 존재(`SimulationService.start/stream/get_result`, `generator_service.start_generation/stream/get_detail`) | `domain/*/service/` |
| 도메인 실행 인터페이스 | 둘 다 `asyncio.create_task` 백그라운드 + `run_id`/`generation_id` 반환 + SSE(`event/stage/pct`) + 메모리 store 조회 | `simulation_service.py:66`, `generator_service.py:43` |
| 채팅 UI | 단일 `/chat` 페이지, SSE 파싱(`{token/meta/done}`), 출처 배지(management/clio) | `frontend/src/app/chat/page.tsx` |
| 인라인 위젯 선례 | `DebatePanel` — 채팅 안에서 토론을 SSE로 실행·누적·결과 콜백. 위젯의 레퍼런스 패턴 | `components/simulator/DebatePanel.tsx` |
| 채팅 DB | `chat_sessions` 테이블 존재(`project_id` FK + `messages` JSONB). **라우터에서 미사용**(`/sessions` 빈 구현) | `core/models.py:179` |
| 플로팅 UI | **구현 완료**. 우측 통합 센터(채팅·알림, 접이식)가 AppLayout에 상시 렌더 — 구 NotificationBell·FloatingChat·ProjectChatSection을 대체 | `components/center/Center.tsx`·`components/center/ChatCenter.tsx` |

> 아래 3~7장은 2026-06-23 최초 설계 당시의 제안 내용(LangGraph route→delegate 기반 오케스트레이터 구상)이다. 실제로는 이후 **deepagents 기반 통합 에이전트로 클린 재작성**되어 8장의 최종 구조로 대체됐다. 설계 배경·시나리오 서술은 여전히 유효하므로 남겨두되, "as-is" 갭은 8장 기준으로 이미 해소됐다.

---

## 3. 목표 아키텍처 (to-be)

```
[프론트]                          [백엔드: /api/chat]
 채팅 탭(/chat)  ─┐
 플로팅 챗봇      ─┼─ SSE ─▶  오케스트레이터 (LangGraph)
 (시뮬/제너 화면)  ┘            route → delegate → stream → (HITL) → answer
       ▲                              │
       │ 위젯 envelope                ├─ tool: run_simulation   ─▶ SimulationService
       │ (progress·result·approve)    ├─ tool: run_generator    ─▶ generator_service
       └──────────────────────────────┤─ tool: ask_management   ─▶ build_management_agent (완성)
                                       │
                              세션/스레드 store ──▶ chat_sessions (project_id 귀속)
                                       checkpointer ──▶ AsyncPostgresSaver (HITL 재개)
```

설계 원칙은 매니지먼트 spec을 그대로 승계한다.

- **서브에이전트 = 도구 하나** — 각 도메인을 `build_*_agent(settings)→Callable`로 감싸 오케스트레이터에 tool로 등록. 화면·API 변경 없이 붙인다.
- **읽기 + 행동 제안** — 채팅은 실행을 **제안**하고, 실제 집행(생성물 publish/advertise, 캠페인 변경)은 기존 **승인→executor 경로**로만. 위젯에 승인 버튼.
- **무키 폴백** — LLM 키 없으면 키워드 라우팅 + 도구 요약으로 degrade(재현성 유지).
- **숫자는 실측, 판단은 지식** — 도메인 도구가 돌려준 수치만 인용, LLM이 지어내지 않음.

---

## 4. 핵심 시나리오

이 챗봇의 차별점은 단발 질의응답이 아니라 **세 도메인을 왕복하는 흐름**이다. 두 시나리오가 중심.

### 4.1 개선 루프 (closed loop) — 제품 핵심

시뮬레이션의 약점 → 제너레이터 개선 → 재시뮬을 **채팅이 제안하며** 왕복한다.

```
시뮬 실행 ─▶ [채팅] "구매의도 낮음. 개선 시안 만들까요?" ─(수락)─▶ 제너 개선모드
   ▲                                                                     │
   └──── [채팅] "시안 나옴. 다시 반응 볼까요?" ◀─(수락)── 제너 완료 ◀─────┘
   (목표 도달 또는 최대 3회까지 반복)
```

- **루프의 두뇌는 오케스트레이터** — 시뮬 결과를 제너 개선모드 입력으로, 제너 결과(시안)를 시뮬 입력으로 변환하고 제안 타이밍을 관리한다. 시뮬·제너 자신은 도구(자판기)일 뿐.
- **데이터 통로 기존재** — 제너 개선모드는 `simulation_summary`·`fix_requests`·`existing_ad_s3_key`를 받고, 시뮬은 `ad_image_url`을 받는다. 시뮬 결과↔제너 입력 변환만 오케스트레이터가 채우면 된다.
- **루프 정책 (확정)**
  - 매 전환은 **사람 수락(HITL)** — 자동 무한 반복 없음. "제안 → 수락" 단계가 매번 들어간다.
  - **최대 3회** 왕복. 초과 시 중단하고 현황을 요약한다.
  - **목표 조기 종료** — 3회 전에 목표(판정 기준은 6장 열린 질문) 도달 시 "이제 충분합니다"로 종료.

### 4.2 백그라운드 실행 + 플로팅 가시성

긴 실행을 걸어두고 다른 일을 하다가, 플로팅에서 진행 상황을 본다.

```
시뮬 백그라운드 시작(run_id 보관) ─▶ 그 사이 채팅으로 매니지먼트 질의
                                       │
   우측 하단 플로팅 클릭 ◀─────────────┘
   └─▶ 진행 중 작업: "시뮬레이션 🔄 62% (반응 중)"   ← 스피너+진행률(SSE 구독)
   └─▶ 완료 시 "결과 보기" 위젯으로 전환
```

- `start()`가 즉시 run_id를 반환하므로 백그라운드 실행은 구조적으로 가능하다. 플로팅은 진행 중 작업의 SSE를 구독해 스피너·진행률을 표시.
- 동시에 여러 작업이 돌 수 있으므로 플로팅은 **진행 중 작업 트레이(목록)** 형태로 둔다.

---

## 5. 작업 목록과 우선순위

사용자 제시 6항목(U)에 더해, 조사로 도출한 추천 항목(R)을 포함한다. 우선순위는 **의존성 + 가치** 기준으로 P0→P3 단계로 묶었다(단계 순서가 곧 착수 순서).

### Phase P0 — 그릇 만들기 (영속화·프로토콜)

위젯·오케스트레이터가 올라탈 토대. 도메인 연결 없이도 단독 진행 가능해 가장 먼저.

| # | 항목 | 출처 | 의존 | 규모 |
| --- | --- | --- | --- | --- |
| P0-1 | **채팅 내역 DB 연결** — `/sessions`·`/messages` 실구현, `chat_sessions` 읽기/쓰기 | U6 | — | M |
| P0-2 | **프로젝트 귀속** — 세션에 `project_id` 저장·필터, 프로젝트 내역에 채팅 노출 | U5 | P0-1 | S |
| P0-3 | **세션/스레드 관리 + checkpointer 영속화** — 대화 thread_id, HITL 재개용 `MemorySaver→AsyncPostgresSaver` | R | P0-1 | M |
| P0-4 | **스트리밍/메시지 프로토콜 표준화** — `{token/meta/done}`(텍스트)와 `{event/stage/pct}`(실행)를 하나의 위젯 envelope로 통합 | R | — | M |

### Phase P1 — 오케스트레이션 성립 (핵심)

세 도메인을 한 채팅에서 부르는 본체. 이 단계가 끝나면 "합친 챗봇"이 동작한다.

| # | 항목 | 출처 | 의존 | 규모 |
| --- | --- | --- | --- | --- |
| P1-1 | **오케스트레이터 본체** — LangGraph route→delegate. 현재 키워드 if 분기를 대체, 도구 호출 그래프로 | R ★ | P0-4 | L |
| P1-2 | **시뮬·제너 서브에이전트** — `build_simulation_agent`/`build_generator_agent`(매니지먼트 패턴 복제), read/run 도구 노출 | R ★ | — | L |
| P1-3 | **3개 기능 연결** — 서브에이전트를 오케스트레이터 tool로 등록(매니지먼트는 등록만, 시뮬·제너는 P1-2 후) | U2 | P1-1·P1-2 | M |
| P1-4 | **컨텍스트 주입** — `project_id`, 직전 시뮬/생성 결과 ID를 도구 인자로 전달(맥락 있는 위임) | R | P0-2 | S |
| P1-5 | **플로팅 챗봇 UI 셸** — 채팅 탭 유지 + 시뮬/제너 화면 우측 하단 플로팅(접힘/펼침, z-40) | U1 | — | M |

### Phase P2 — 실행 경험 (위젯·백그라운드)

채팅 안에서 기능이 "보이게" 도는 단계.

| # | 항목 | 출처 | 의존 | 규모 |
| --- | --- | --- | --- | --- |
| P2-1 | **기능 실행 위젯** — 시뮬 진행률+KPI, 제너 후보 카드, 매니지 before/after를 메시지에 인라인. `DebatePanel` 패턴 차용 | U3 | P0-4·P1-3 | L |
| P2-2 | **백그라운드 실행 + 진행 중 작업 트레이 + 완료 알림** — 실행 걸어두고 다른 대화 진행, 플로팅에 스피너·진행률(4.2), 완료 시 채팅에 결과 푸시 | U4·R | P1-3·P1-5·P0-3 | M |
| P2-3 | **HITL 승인 흐름 통합** — 행동 제안(생성물 집행·캠페인 변경)을 위젯 승인 버튼→기존 approval/executor로 | R | P2-1 | M |
| P2-4 | **백그라운드 실행 테스트** — 각 도구의 start→stream→result 경로 통합 테스트(서버 재시작 시 소실 케이스 포함) | U4 | P1-3 | M |
| P2-5 | **개선 루프 컨트롤러 ★** — 시뮬↔제너 왕복(최대 3회·목표 조기종료), 매 전환 HITL 제안·수락, 시뮬↔제너 입출력 변환(4.1) | 신규 ★ | P1-3·P2-1·P2-3 | L |

### Phase P3 — 안전·품질

운영 진입 전 가드.

| # | 항목 | 출처 | 의존 | 규모 |
| --- | --- | --- | --- | --- |
| P3-1 | **무키 폴백 모드** — LLM 키 없을 때 키워드 라우팅 degrade(매니지 패턴 전 도메인 확장) | R | P1-1 | S |
| P3-2 | **권한·비용·한도 가드** — 채팅 트리거 시 `sample_size`·생성 비용 상한, 플랜별 제한 | R | P1-3 | M |
| P3-3 | **라우팅 정확도 eval + 트레이싱 일원화** — 어떤 질문이 어느 도메인으로 가는지 평가셋, 오케스트레이터+서브에이전트 LangSmith trace 통합 | R | P1-1 | M |
| P3-4 | **에러·취소·재시도** — 긴 실행 중 취소, 실패 복구, rate-limit 표면화 | R | P2-2 | S |

### 사용자 6항목 매핑

| 사용자 항목 | 배치 |
| --- | --- |
| 1. 플로팅 챗봇 | **P1-5** |
| 2. 각 기능 연결 | **P1-3** (전제 P1-1·P1-2 추가) |
| 3. 채팅용 위젯 | **P2-1** |
| 4. 백그라운드 실행 테스트 | **P2-4** (+ P2-2 알림으로 확장) |
| 5. 프로젝트 귀속 | **P0-2** |
| 6. 채팅 내역 DB | **P0-1** |
| (신규) 개선 루프 | **P2-5 ★** |

> 핵심 보강 — 사용자 6항목 중 "2. 각 기능 연결"은 사실상 **P1-1 오케스트레이터 본체**와 **P1-2 시뮬·제너 서브에이전트**가 선행돼야 한다. 이 둘이 빠지면 지금처럼 키워드 if 분기에 머문다. 그래서 R 항목 중 P1-1·P1-2를 ★ 최우선으로 표시했다.
>
> 개선 루프(4.1)는 6항목엔 없던 **제품 핵심 요구**다. 시뮬·제너 연결(P1-3)·위젯(P2-1)·HITL(P2-3) 위에 올라가는 컨트롤러(P2-5)이며, 이 셋이 끝나는 즉시 착수한다.

---

## 6. 핵심 설계 결정

- **오케스트레이터 LLM = OpenAI** (확정) — 도구 호출 안정성 기준. 매니지 어시스턴트와도 일치해 스택 단순.
- **호출 방식 = 혼합** (확정) — 매니지먼트는 **서브에이전트**(자체 LLM 루프) 그대로 두고, 시뮬·제너는 **단순 도구 함수**(자판기)로 부른다. 루프의 판단을 오케스트레이터가 전담하므로 시뮬·제너에 별도 LLM을 둘 필요가 없다.
- **개선 루프 = HITL 상태머신** (확정) — 오케스트레이터가 시뮬↔제너 전환을 관리. 최대 3회, 매 전환 사람 수락, 목표 도달 시 조기 종료(4.1).
- **오케스트레이터 패턴** — 매니지먼트의 LangGraph ReAct를 복제. 도구 중 매니지는 서브에이전트(에이전트-of-에이전트), 시뮬·제너는 함수.
- **스트리밍 envelope** — 텍스트 토큰과 실행 이벤트가 한 SSE 스트림에 섞인다. 메시지에 `kind`(text·widget·approval)를 달아 프론트가 분기 렌더. P0-4가 이걸 정의.
- **백그라운드 결과 내구성** — 현재 메모리 store는 서버 재시작 시 소실. 시뮬은 선택적 DB 영속화가 있으나 제너/오케스트레이터 스레드는 없음 → P0-3에서 checkpointer·세션을 DB로.
- **집행 분리** — 채팅은 생성물 publish/advertise·캠페인 변경을 **절대 직접 호출하지 않는다**. 제안→승인→executor 경로만(매니지 불변 규칙 승계).

---

## 7. 열린 질문 / 리스크

- **목표 도달 판정 기준** — 루프 조기 종료(4.1)를 어떤 수치로? `objective_fit` 등급(높음)인지, 구매의도·클릭의향 임계값인지. **루프 착수 전 합의 필요.**
- **플로팅 ↔ 탭 상태 공유** — 같은 세션을 플로팅과 `/chat` 탭이 공유하는가, 분리하는가.
- **비용** — 루프 최대 3회면 시뮬(최대 200 페르소나)·이미지 생성이 최대 3쌍 실행된다. P3-2 가드 없이는 과금 위험.
- **DB 마이그레이션** — `chat_sessions` 활용·KB 테이블·checkpointer 테이블은 공통부(Alembic) 변경 → 사전 공지 필요(협업 규칙).

> 결정 완료 — 오케스트레이터 LLM(OpenAI)·호출 방식(혼합)·루프 정책(3회·HITL·조기종료)은 6장으로 이관.

---

## 8. 구현 현황 (2026-07-09 갱신 — 최종 구조)

**오케스트레이터 본체는 2026-06-23 당시 구상(위 3~7장, `domain/chat/orchestrator.py` 기반 LangGraph route→delegate)에서 이후 전면 교체됐다.** 2026-06-30 커밋 `4c3e7c8f`(`delete: 레거시 채팅 오케스트레이터·deep_agent 제거`)로 `domain/chat/orchestrator.py`(1073줄)와 손수 짠 `api/assistant/deep_agent.py`(828줄) 2-레이어 구조를 모두 삭제하고, **`deepagents` 기반 통합 에이전트 한 번 호출**로 클린 재작성했다(배경은 `docs/chat/deep-agent-migration/최종구현 계획서.md`, 전환 기록은 `docs/chat/deep-agent-migration/checklist.md` 1~4단계 참고).

**현재 오케스트레이터 본체** — `backend/api/assistant/deep_agent_builder.py::build_unified_chat_agent(settings)`가 다음을 한 번 조립한다.

```python
create_deep_agent(
    model=build_chat_llm(settings, ...),        # domain/chat/llm.py, provider=openai, model=gpt-4.1
    tools=build_chat_tools(settings),            # api/assistant/subagent_tools.py, @tool 31개
    system_prompt=CHAT_POLICY,                   # api/assistant/prompts.py
    middleware=[ChatStateMiddleware()],           # api/assistant/chat_state.py
    subagents=[],                                 # 의도적 — 아래 참고
    checkpointer=build_checkpointer(settings),    # domain/management.wiring 재사용
)
```

키 없음/mock이면 `None`을 반환해 `chat.py`가 CLIO 폴백으로 degrade한다(deepagents 자체가 없거나 충돌하면 `langchain.agents.create_agent`로 폴백).

- **`subagents=[]`는 의도적 설계 결정이다.** deepagents 고유의 서브에이전트 기능(`CompiledSubAgent`)은 부모-자식이 `messages`만 주고받는 얕은 위임이라, management 도메인이 쓰던 thread_id 고정·memory_context 주입·citations/suggested_action→meta 변환 같은 어댑터 로직이 그대로는 옮겨지지 않는다. 대신 **얇은 `@tool`로 도메인을 감싸 상태(`Command(update={"sub_meta": ...})`)에 결과를 쌓는 방식**을 택했다.
- **도구는 두 층으로 나뉜다** (`api/assistant/subagent_tools.py::build_chat_tools`).
  - **위임 tool** — `ask_management`/`ask_simulation`/`ask_generator`/`ask_general_knowledge`. 조회·해석·조언만 하고 실행하지 않는다.
  - **위젯 tool** — `run_simulation`/`run_generation` 등. 화면에 카드(위젯) 신호만 적재하고, 실제 실행은 화면이 별도 REST 호출로 수행한다(채팅이 직접 실행 API를 호출하지 않는다는 6장 "집행 분리" 원칙 그대로 승계).

**Phase P0~P2 항목 실제 완료 현황** (3~7장 표의 사용자 6항목 매핑 기준)

- ✅ P0-1·P0-2 채팅 내역 DB·프로젝트 귀속 — `chat_sessions`/`chat_messages` 실사용, 세션·프로젝트 필터 동작.
- ✅ P0-3 세션/체크포인터 영속화 — `build_checkpointer(settings)`(로컬 `MemorySaver`/운영 `AsyncPostgresSaver`).
- ✅ P1-1·P1-2·P1-3 오케스트레이터 본체·3도메인 연결 — 위 `build_unified_chat_agent` 구조로 대체 완료(LangGraph route→delegate 노드 방식이 아니라 deepagents 통합 에이전트 방식으로).
- ✅ P1-5 플로팅 챗봇 UI — `components/center/Center.tsx`·`ChatCenter.tsx`(우측 통합 센터, 접이식)로 구현 완료. 위 2장 표도 갱신됨.
- ✅ P2-1 기능 실행 위젯 — `meta.cards`(`ActionCards.tsx`, RESULT/REVIEW/ACTIONBAR) + 기존 14개 위젯 그대로 보존.
- ⬜ P2-5 개선 루프 컨트롤러(시뮬↔제너 최대 3회 왕복·목표 조기종료) — 미착수. 현재 위임/위젯 tool 구조 위에 별도로 얹어야 한다.
- ⬜ `classify_intent` 명시 노드 · 엔드포인트 `/api/assistant/chat` — 채택하지 않음. LLM이 시스템 프롬프트(`CHAT_POLICY`) 기준으로 tool 호출을 직접 판단하는 방식으로 대체돼 더 이상 유효한 목표가 아니다.

---

## 9. 참고

- 선행 spec — [docs/superpowers/specs/2026-06-21-chat-management-agentic-rag.md](../superpowers/specs/2026-06-21-chat-management-agentic-rag.md)
- 매니지 서브에이전트 — `backend/domain/management/assistant/{agent,graph,tools,retriever}.py`
- 채팅 라우터·모델 — `backend/api/routers/chat.py` · `backend/core/models.py:179`
- 통합 오케스트레이터(현재 본체, 8장) — `backend/api/assistant/deep_agent_builder.py` · `backend/api/assistant/subagent_tools.py` · `backend/api/assistant/prompts.py`
- 도메인 실행 진입점 — `backend/domain/simulation/service/simulation_service.py:66` · `backend/domain/generator/service/generator_service.py:43`
- 프론트 — `frontend/src/app/chat/page.tsx` · `frontend/src/components/simulator/DebatePanel.tsx` · `frontend/src/components/AppLayout.tsx` · `frontend/src/components/center/Center.tsx`
</content>
