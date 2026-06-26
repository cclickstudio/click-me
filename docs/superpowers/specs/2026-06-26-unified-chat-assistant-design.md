# 통합 채팅 어시스턴트 설계 — 시뮬·생성·관리 한 입구 (AI 비서)

문서 v0.1(작성 중) · 2026-06-26 · 소유 generator(token-opt 브랜치) · 관련 문서: `docs/chat/context-notes.md`·`docs/chat/checklist.md`, `docs/superpowers/specs/2026-06-21-chat-management-agentic-rag.md`, `docs/superpowers/specs/2026-06-22-chat-management-execution-handoff-design.md`

> **한 줄 요지** — 라이브 채팅을 이미 만들어진 오케스트레이터(교통정리)에 연결해, **하나의 채팅에서 시뮬 → 결과 → 개선**까지 잇는다. 단순 응답이 아니라 **AI 비서**처럼 다음 단계를 먼저 제안한다. **"비서가 먼저 제안하고, 실행은 사용자가 정한다."**

---

## 0. 배경 / 문제

이 브랜치(feat/generator-token-opt)는 dev 머지로 generator·management·simulation이 한곳에 모인 **통합 지점**이다. 그런데 채팅 입구가 **두 갈래로 따로 논다.**

1. **라이브 입구** `api/routers/chat.py` `/complete` — 프론트가 실제로 부르는 곳. `_is_management()` 키워드면 관리 에이전트, 아니면 CLIO(Gemini) 스트리밍. **그게 전부 — 생성·시뮬은 못 한다.** 코드 주석(53행)도 "임시 연결"이라 적혀 있다.
2. **설계된 오케스트레이터** `api/assistant/` — 의도분류 → registry 디스패치(단일 패스). GENERATE(슬롯필링)·MANAGE(에이전틱 RAG)가 이미 등록돼 있고, 중립 계약(`core/assistant_contracts.py`)으로 ASK/TRIGGER/ANSWER 액션까지 갖췄다. **그런데 라이브가 이걸 호출하지 않는다.**

즉 **행동하는 채팅을 만들 부품(오케스트레이터+서브에이전트)은 다 있는데, 라이브가 그 부품을 안 끼우고 있다.**

추가로 비어 있는 것.

- **SIMULATE 미등록** — registry에 시뮬 핸들러가 없고, 의도분류기에도 시뮬 키워드·설명이 없다. 사용자가 원하는 "시뮬+생성+관리" 중 시뮬이 빠져 있다.
- **채팅 내 이미지 첨부 없음** — 시뮬은 광고 이미지가 **필수**, 생성은 상품/로고가 **선택**인데, 현재 채팅은 글자만 주고받는다.
- **시뮬 → 개선 바통터치 미연결** — 생성 담당엔 개선모드(`improve_context`)가 이미 있으나, 시뮬 결과를 그 입력으로 넘기는 연결이 없다.

**목표** — 라이브를 오케스트레이터로 단일화(P1)하고, 사용자가 그린 핵심 흐름(시뮬→결과→개선, P2)을 동작시킨다. 관리는 이미 만들어진 담당을 붙이는 수준(P3)으로 둔다. **AI 비서 선제성**(다음 단계 자동 제안)을 설계 전반의 기본값으로 삼되, **실행·승인은 사용자**(관리 위험 조치는 HITL 게이트 유지).

---

## 1. 아키텍처 / 경계

채팅 한 턴이 들어오면 이렇게 흐른다. **교통정리(오케스트레이터)는 한 번만 판단하고 알맞은 담당에게 넘긴다(루프 없음).**

```
사용자 메시지 (+ 이미지 첨부 가능)
   │
   ▼
[라이브 입구  api/routers/chat.py /complete]   ← 전송계층(SSE·스트리밍 담당)
   │  ChatRequest → SubagentRequest 로 변환
   ▼
[교통정리  api/assistant Orchestrator.run_turn]   ← 단일 패스(1턴=1처리)
   │  의도분류 1콜(Gemini, 키 없으면 키워드)
   ├─ GENERATE → [생성 담당]  슬롯필링 (상품명·타깃… 모으고 +상품/로고 이미지 선택)
   ├─ SIMULATE → [시뮬 담당]  ★P2 신규 (광고 이미지 필수)
   ├─ MANAGE   → [관리 담당]  에이전틱 RAG(실측+KB, HITL)
   └─ ADVISE   → (핸들러 없음) → 입구가 CLIO(일반 상담)로 폴백
   │
   ▼  각 담당이 돌려주는 표준 결과 = SubagentResult(action, message, started_event?)
[입구가 action 을 SSE 로 변환]
   ├─ ANSWER  → 메시지 토큰 스트리밍            (관리 즉답·인용)
   ├─ ASK     → 되묻기 질문 스트리밍            ("광고 이미지를 넣어주세요")
   └─ TRIGGER → started_event(stream_url) 방출  → 프론트가 그 잡 SSE 구독(로딩→결과)
```

### 북극성 흐름이 이 안에서 도는 법 (시뮬 → 결과 → 개선)

```
"시뮬 돌려줘" (이미지 없음)  → 시뮬 담당 → ASK "광고 이미지를 넣어주세요"
"(이미지 첨부) 이걸로"        → 시뮬 담당 → TRIGGER → 시뮬 잡 → 로딩 → 결과
   │  ★AI 비서: 결과 끝에 "개선할까요?" 를 자동 제안
   ▼  사용자 수락
개선 라우팅 → 생성 담당(개선모드)
   improve_context = { s3_key=그 광고 이미지, simulation_summary=시뮬 결과 }
   → TRIGGER → 개선 이미지 잡
```

핵심 — 시뮬에 올린 **그 광고 이미지(s3_key)** 를 흐름 내내 들고 다니다가 개선모드 입력으로 그대로 넘긴다. 그래야 "원본 이미지 + 시뮬 결과"를 같이 보고 개선 이미지를 만든다.

### 경계 원칙 (넘지 말 선)

- **도메인 격리** — 교통정리(`api/assistant`)는 각 도메인의 `build_*` 함수만 조립(`wiring.py`)한다. **도메인끼리 직접 import 금지**, 교환은 중립 계약 `core/assistant_contracts.py`(SubagentRequest/Result·Intent·Action·StartedEvent)로만. 시뮬→개선 바통터치도 교통정리 레이어에서 contract로 잇는다(시뮬 도메인이 생성 도메인을 직접 부르지 않음).
- **단일 패스(루프는 안쪽에만)** — 교통정리는 1턴에 한 번만 판단하고 끝. 깊은 추론·도구 루프는 **서브에이전트 안에만**(예: 관리 RAG). 최상위가 루프를 돌면 예측 불가·비용 폭발.
- **전송계층 책임 분리** — 스트리밍(SSE)·CLIO 폴백·이미지 업로드 수신은 **입구(chat.py)** 가 맡는다. 서브에이전트는 "무엇을 할지(action)"만 돌려주고 "어떻게 흘려보낼지"는 모른다. 그래서 담당 로직은 전송 방식과 무관하게 테스트 가능.
- **잡 핸드오프는 stream_url 로** — 오래 걸리는 일(생성·시뮬)은 담당이 잡을 시작하고 `started_event(stream_url)`만 돌려준다. 진행상황·결과는 프론트가 그 주소를 따로 구독(기존 생성 스트림 패턴 재사용).

---

## 2. 컴포넌트 설계 — P1 (라이브를 오케스트레이터로 연결)

> P1 한 줄 — 입구(`chat.py`)가 자기 멋대로 하던 키워드 라우팅을 버리고 **교통정리(`Orchestrator.run_turn`)를 거치게** 한다. 새로 만드는 건 거의 없고 **연결**이 핵심. 단 **관리 패리티(멀티턴·기록)는 반드시 보존**.

### 2.1 입구 `chat.py /complete` 재배선

| | 내용 |
|---|---|
| **뺀다** | `_is_management()`·`_MGMT_KEYWORDS`·`_get_assistant()`·인라인 관리 분기 |
| **넣는다** | 오케스트레이터 1회 빌드·캐시(`build_assistant(settings)`), ChatRequest→SubagentRequest 변환, `run_turn()` 호출, action→SSE 매핑 |
| **유지한다** | CLIO(Gemini) 스트리밍 = ADVISE 폴백 경로 그대로 |

### 2.2 ChatRequest → SubagentRequest 변환

| SubagentRequest | 출처 | 비고 |
|---|---|---|
| `messages` | `body.messages` | ChatMessage 호환 |
| `session_id` | `body.session_id` | 멀티턴 thread 상관키 |
| `context_ad_id` | `body.context_ad_id` | 관리 시뮬 예측 연결 |
| `improve_context` | `body.improve_context` | 있으면 교통정리가 GENERATE로 직행(이미 구현) |
| `user_id`·`org_id`·`project_id` | `None` | **인증 미적용 페이즈** — 빈 값 |

### 2.3 action → SSE 매핑 (입구 책임)

| 결과 | SSE로 내보내는 것 |
|---|---|
| `result is None` (ADVISE/미등록) | 기존 **CLIO 스트리밍**(Gemini) 그대로 |
| `ANSWER` | `{"meta":…}` → `{"token":…}` 청크 (관리 즉답·인용) |
| `ASK` | `{"token": 질문}` 청크 ("광고 이미지를 넣어주세요" 등) |
| `TRIGGER` | `{"meta":…}` → **`{"started": started_event}`** → `{"token": 확인메시지}` |
| (공통) | 끝에 `{"done": true}` |

### 2.4 ✅ 관리는 "지금 길 그대로" (회귀 함정 회피)

라이브 관리 경로는 이미 멀티턴(`thread_id`)·기록(`record_turn`)·HITL을 갖춰 잘 돈다. 교통정리의 기존 관리 핸들러엔 그게 없어, 무리하게 갈아끼우면 관리가 회귀한다.

**결정 — 관리는 건드리지 않는다.** 입구(`chat.py`)가 **관리 키워드면 기존 관리 경로로 그대로**, 그 외는 교통정리로 보낸다. 관리 회귀 위험·관리 팀 의존이 둘 다 없어진다(혼자 완성 가능).

- `chat.py` 분기 — ① `_is_management` → **기존 관리 경로(무변경)** ② else → `orchestrator.run_turn`(GENERATE 처리 · SIMULATE 소켓 · ADVISE→CLIO).
- 교통정리의 MANAGE 등록은 남겨둬도 무방(관리는 ①에서 먼저 잡혀 도달 안 함). 또는 wiring에서 GENERATE만 등록.
- 관리를 교통정리로 통합(패리티 보강)하는 일은 **B(핸드오프) — 관리 팀 후속**으로 미룬다.

### 2.5 새 SSE 이벤트 `started` — 프론트 계약 (조율 지점)

TRIGGER일 때 입구가 `data: {"started": {event, job_id, stream_url, domain}}`를 방출 → 프론트가 `stream_url`을 구독해 진행/결과 표시. **현재 프론트 `/chat`은 이 이벤트를 모름** → 프론트와 이벤트 포맷 합의 필요(P1 산출물에 프론트 작업 1건 포함).

### 2.6 엣지/주의

- **인증 공백** — `user_id=None`이라 생성은 프로젝트 저장 단계에서 "로그인 필요" 안내로 막힌다. P1 허용 범위(슬롯 되묻기까지는 동작), 프로젝트 연결은 인증 도입 후.
- **폴백 불변식** — 의도분류 실패·서브에이전트 예외는 키워드/CLIO로 흘려 **채팅을 끊지 않는다**(기존 try/except 철학 유지).
- **improve_context** — 있으면 교통정리가 GENERATE로 직행(orchestrator 기구현). P1은 통과만 하면 됨(시뮬→개선 자동연결은 P2).

### 2.7 (예고) AI 비서 확장 — 롱텀 메모리(LTM) [P3]

> 자리만 잡는 항목. 정식 상세는 P1·P2 확정 후.

- **무엇** — 세션을 넘어 사용자를 기억(브랜드 색·자주 쓰는 타깃·과거 캠페인 결과 등). "에이전트를 넘어 **AI 비서**" 비전의 핵심.
- **재사용** — 바닥부터 만들지 않는다. 관리 spec(`2026-06-24-management-agentic-rag-memory-eval.md`)이 **STM=체크포인터 / LTM=전용 테이블(asyncpg)** 을 이미 설계 확정(구현 대기). 그 설계를 가져온다.
- **이 채팅에 맞게 일반화** — 현재 LTM 설계는 관리 전용. 통합 채팅이 *어느 담당으로 가든* 기억하려면 LTM을 **도메인 중립(교통정리/세션 레이어)** 으로 확장 필요.
- **P1과의 구분** — P1 관리 패리티 = STM(대화 내 멀티턴) 보존. LTM은 그 위 **별도 기능**. 섞지 않는다.
- **선제성 연결** — LTM이 있으면 "저번 그 캠페인 개선안 이어서 볼까요?"처럼 과거 맥락 기반 제안 가능 → AI 비서 선제성 강화.

---

## 3. 컴포넌트 설계 — P2 (시뮬 → 결과 → 개선, 북극성 흐름)

> 좋은 소식 — 시뮬도 생성과 **똑같은 잡 패턴**을 이미 갖췄다. `POST /api/simulation`(start→run_id) · `/{run_id}/stream`(진행) · `/{run_id}/result`(결과). 시작 입력도 광고 이미지(`ad_image`/`ad_image_url`/`ad_image_key`)를 받는다. **새 인프라 거의 불필요 — 연결이 핵심.**

### 3.1 채팅 이미지 첨부 (시뮬·생성 공통 선행)

- **계약 변경(🤝 조율)** — `SubagentRequest`에 이미지 첨부 필드 추가(예: `attached_image_s3_key` 또는 `attachments: list[str]`). 공통 계약(`core/assistant_contracts.py`)이라 변경 전 공지.
- **업로드 경로** — 채팅 첨부 → S3 → s3_key. 생성의 임시 업로드(`store_temp_image`, S3) 패턴 재사용 가능.
- **프론트** — `/chat` 첨부 UI(시뮬=광고 이미지 **필수**, 생성=상품/로고 **선택**).

### 3.2 SIMULATE 서브에이전트  (🟨 시뮬 도메인 — sim팀 소유)

- **신규** — `domain/simulation`에 chat 핸들러 어댑터 `build_simulation_chat_agent` → `SubagentResult`.
- **로직** — 첨부 이미지 없음 → **ASK**("광고 이미지를 넣어주세요"). 있음 → `_service.start(req)` → **TRIGGER** + `StartedEvent(stream_url=/api/simulation/{run_id}/stream, domain="simulation")`.
- **입력 매핑** — 첨부 s3_key → `ad_image_key`/`ad_image_url`, 최근 사용자 텍스트 → `ad_content`(카피). **`ad_id` 규칙**(신규 채팅 시뮬의 식별자)은 sim팀과 조율.
- **등록** — `wiring`에 `Intent.SIMULATE`, `intent.py`에 시뮬 키워드("시뮬", "반응 예측", "테스트해봐"…) + LLM 분류 설명.
- ⚠️ **소유권** — 이 핸들러는 시뮬 도메인 코드 → **sim팀이 소유·구현**. generator(우리)는 공통 계약·교통정리 등록 줄만 손댄다(협업 규칙: 타 도메인 내부는 읽기만).

### 3.3 시뮬 → 생성(개선) 바통터치  (AI 비서 선제성)

- **자동 제안** — 시뮬 결과가 나오면 "개선할까요?"를 먼저 노출. **위치 = 프론트**(시뮬 stream 완료 감지 → 자동 노출). 선제성은 UX이고 전송/UX는 프론트 책임(경계 원칙).
- **수락 시** — 프론트가 `improve_context = {s3_key=그 광고 이미지, simulation_summary=/result 요약, product_name}` 구성 → 채팅 메시지로 전송 → 교통정리가 **GENERATE 직행**(orchestrator 기구현) → `slot_agent` improve 분기 → **개선 이미지 TRIGGER**.
- **핵심** — `s3_key` = 사용자가 시뮬에 올린 **그 이미지**(흐름 내내 보관). `simulation_summary`는 `/result`에서.
- **기존 자산 재사용** — 시뮬 페이지에 이미 "개선" 버튼 + `improve_context` 패턴 존재. 이걸 채팅판으로 옮기는 셈.

### 3.4 엣지/주의

- 시뮬 API는 이미지 optional이지만 **채팅 시뮬은 이미지 필수**(핸들러 게이트) — 개선 참고자료로 필요하기 때문(§0·결정).
- `ad_id`·이미지 업로드 위치·시뮬 결과 요약 포맷은 **sim팀 조율 항목**.

---

## 4. 구현 범위 A — 내가(generator) 상세 구현·코딩

> 전략 — **혼자 완성 가능한 골격 + 내 도메인 흐름**까지만 코딩한다. 남의 도메인(시뮬·관리)은 손대지 않고 **빈 소켓 + 핸드오프 지시서**(§5)만 남긴다. 관리 팀이 했던 "import-ready"와 같은 방식.

### 4.1 만드는 것 (혼자 완결)

- **채팅 골격** — `chat.py`가 ① 관리 키워드면 기존 관리 경로(무변경) ② 그 외는 `Orchestrator.run_turn`을 거치도록 배선(§2.1·2.4).
- **생성·개선 흐름 배선** — 이미 있는 `build_generation_chat_agent`·`slot_agent`(improve)를 교통정리에 연결해 실제로 동작(슬롯 되묻기 → 생성 TRIGGER, improve_context → 개선 TRIGGER).
- **action→SSE 매핑**(§2.3) + **`started` 이벤트**(§2.5)와 그걸 받는 **최소 프론트**(생성 진행 구독).
- **SIMULATE 빈 소켓** — 교통정리에 "시뮬은 여기로"만 표시(미등록 시 친절한 "시뮬 채팅 준비 중" 스텁 또는 ADVISE 폴백). 실제 담당은 §5.1.

### 4.2 내가 손대는 파일 (내 소유 / 공통은 공지)

| 파일 | 변경 | 구분 |
|---|---|---|
| `api/routers/chat.py` | 분기 배선 + action→SSE | 채팅 입구(내가 주도) |
| `api/assistant/wiring.py` | GENERATE 등록 확인 + SIMULATE 소켓 주석 | 조립(내가) |
| `domain/generator/chat/*` | 필요 시 미세 조정(대개 그대로) | 🟩 generator 소유 |
| `core/assistant_contracts.py` | 이미지 첨부 필드 추가 | 🤝 **공통 — 사전 공지** |
| `frontend .../chat/page.tsx` | `started` 구독 + 생성 이미지 첨부(선택) | 프론트(내가) |

### 4.3 테스트 (검증 가능한 성공 기준 — TDD)

- 라우터: "광고 만들어줘"(정보 부족) → **ASK**, 정보 충족 → **TRIGGER + started**, 일반 질문 → **CLIO 폴백**.
- 관리 무변경 회귀: 관리 키워드 질문이 **기존 경로 그대로**(멀티턴·인용·승인 유지).
- improve_context 주입 → GENERATE 개선 TRIGGER.
- 폴백 불변식: 분류·서브에이전트 예외 시 채팅 안 끊김.
- `ruff` + `pytest tests/generator/` + 라우터 테스트 통과.

### 4.4 스코프 제외 (Won't — 이번에 안 함)

- 시뮬 담당 실제 구현(§5.1, sim팀), 관리의 교통정리 통합(§5.2, 관리팀).
- 롱텀 메모리(LTM, §2.7 — 후속 별도 spec).
- 인증·프로젝트 자동연결(인증 도입 후).
- 채팅 자유발화로 위험 조치 실행(관리 HITL 버튼 원칙 유지).

---

## 5. 구현 범위 B — 핸드오프 기록 ("이 채팅에 당신 도메인을 끼우는 법")

> 골격은 §4로 깔려 있다. 각 팀은 아래 소켓에 끼우기만 하면 된다. **무거운 로직은 각자 도메인, 교통정리엔 등록 한 줄.**

### 5.1 시뮬 팀 — SIMULATE 끼우기

1. `domain/simulation`에 `build_simulation_chat_agent(settings)` 구현 → `async (SubagentRequest) -> SubagentResult`.
   - 첨부 이미지(`req.attached_image_s3_key`) 없으면 `Action.ASK("광고 이미지를 넣어주세요")`.
   - 있으면 `_service.start(req')` → `Action.TRIGGER` + `StartedEvent(event="simulation_started", job_id=run_id, stream_url=f"/api/simulation/{run_id}/stream", domain="simulation")`.
2. `api/assistant/wiring.py`에 `registry.register(Intent.SIMULATE, build_simulation_chat_agent(settings))` **한 줄**.
3. `api/assistant/intent.py`에 시뮬 키워드 + LLM 분류 설명 추가.
4. 조율 필요 — 신규 채팅 시뮬의 `ad_id` 규칙, 시뮬 결과 요약 포맷(§3.3 바통터치가 쓸 `simulation_summary`).

### 5.2 관리 팀 — 교통정리로 통합(후속, 선택)

지금은 관리가 교통정리 밖(기존 경로)에 있어도 정상 동작한다. 합치고 싶을 때.
1. `wiring._build_management_handler`를 라이브 동급으로 보강 — `thread_id=f"mgmt-{session_id}"`·`record_turn`·HITL 메타(§2.4 옛 안 참고).
2. `chat.py`의 `_is_management` 선분기 제거 → 관리도 `run_turn` 경유.
3. 회귀 테스트 — 멀티턴·인용·승인게이트가 통합 후에도 유지되는지.

### 5.3 공통 계약 변경 (🤝 사전 공지)

- `core/assistant_contracts.py` `SubagentRequest`에 이미지 첨부 필드(`attached_image_s3_key: str | None` 등) 추가. 모든 팀이 쓰므로 변경 전 공지 + 한 번에.

### 5.4 프론트 추가 작업

- `/chat` 이미지 첨부 UI(시뮬=필수, 생성=선택).
- `started` 이벤트 수신 → `stream_url` 구독(생성·시뮬 공통).
- 시뮬 결과 완료 감지 → **"개선할까요?" 자동 노출**(선제성) → 수락 시 `improve_context` 구성해 전송(§3.3).

---

> 섹션 0~5 초안 완료. A(§4)는 generator가 바로 착수, B(§5)는 각 팀 핸드오프. 다음 — A를 `writing-plans`로 구현 계획화.
