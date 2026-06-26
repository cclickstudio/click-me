# 채팅 통합 — 컨텍스트 노트

> 목표: 이 브랜치(feat/generator-token-opt)에서 **시뮬·생성·관리를 한 채팅**으로. "말하는 챗"이 아니라 **행동하는 챗**(되묻고 → 잡을 돌리고 → 조치를 제안).

## 🧭 설계 철학 — "에이전트를 넘어 AI 비서"

팀 지향점은 단순 응답/실행 에이전트가 아니라 **AI 비서**다. 차이 = **선제성(proactive)**. 사용자가 다음 행동을 일일이 지시하기 전에, 맥락을 읽고 **다음 단계를 먼저 제안**한다.

- 갈림길마다 기본값은 "비서답게 **먼저 제안**". (예: 시뮬 결과가 나오면 사용자가 안 물어도 "개선할까요?"를 자동으로 띄움.)
- 단 선제성이 강요가 되면 안 됨 — 제안은 하되 **실행·승인은 사용자**(특히 관리의 위험 조치는 HITL 승인 게이트 유지).
- 이 원칙이 향후 "여기서 먼저 제안 vs 기다림" 결정의 기본 기준.

## 🎯 목표 사용자 흐름 (사용자 정의 — 북극성)

채팅창 하나에서 **시뮬 → 결과 → 개선 이미지**까지 한 흐름으로.

1. 사용자: "시뮬레이션 하고 싶어"  → 교통정리 → **시뮬 담당**.
2. 이미지를 안 넣었으면 → **되묻기(ASK)** "광고 이미지를 넣어주세요".
3. 이미지 첨부 후 시작 → **작업시작(TRIGGER)** → 로딩(스트리밍) → 시뮬 결과.
4. 결과 보고 "이 광고 개선하고 싶어" → **생성 담당(개선모드)** 으로 바통터치 → 시뮬 결과를 받아 **개선 이미지 생성(TRIGGER)**.
5. (별개) "새 광고 만들어줘" → 생성 담당이 필요한 데이터 되묻기 + **상품/로고 이미지는 선택 첨부**.

### 이 흐름이 추가로 요구하는 것

- **채팅 내 이미지 첨부**가 필수 기능 — 시뮬은 광고 이미지가 있어야 돌고, 생성은 상품/로고 이미지를 **선택**으로 받음. 현재 채팅은 글자만 주고받음 → 이미지 입력 경로 신설 필요.
- **시뮬 → 생성(개선) 바통터치** — 시뮬 결과(요약 + 이미지 s3_key)를 생성 담당의 `improve_context`로 넘김. 생성 담당엔 개선모드가 이미 있음(slot_agent improve 분기). 시뮬 결과를 그 포맷으로 변환해 넘기는 연결만 필요.

### ✅ 결정된 사항

- **시뮬레이션은 광고 이미지가 필수.** 글(카피)만으로는 안 돌린다. 이미지 없으면 **무조건 되묻기(ASK "광고 이미지를 넣어주세요")**.
  - 이유: 그 광고 이미지가 시뮬의 입력이자 **개선모드의 참고자료**다. 시뮬 결과만으로는 개선 이미지를 못 만들고, 원본 이미지 + 시뮬 결과가 둘 다 있어야 개선이 가능.
  - 함의: 사용자가 시뮬에 올린 **이미지 s3_key를 끝까지 보관**해, 개선 바통터치 때 `improve_context.s3_key`로 그대로 넘긴다(같은 이미지가 시뮬→개선 일관 추적).
- **개선 바통터치 = 자동 제안.** 시뮬 결과가 나오면 사용자가 안 물어도 채팅이 끝에 "개선할까요?"를 **먼저 띄운다**(AI 비서 선제성 원칙). 실행은 사용자가 수락할 때.
- **단계 순서 = P1 먼저.** 사용자 흐름(P2)이 작동하려면 라이브를 교통정리(오케스트레이터)에 연결하는 P1이 선행.

### 열린 질문 (결정 필요)

- 관리(management) 흐름은 사용자가 아직 로직 미파악 → 채팅 연결은 "이미 만들어진 관리 담당을 교통정리에 붙이기"만 하면 되므로 흐름 설계는 후순위.

## 현황 — 채팅 경로가 두 갈래로 따로 논다

1. **라이브 엔드포인트** `api/routers/chat.py` `/complete` — 프론트가 실제로 부르는 곳.
   - `_is_management(text)` 키워드 → 관리 에이전트, 아니면 CLIO(Gemini) 스트리밍. **그게 전부**(생성·시뮬 불가).
   - 관리 경로가 갖춘 것: `thread_id = f"mgmt-{session_id}"`(멀티턴 메모리·checkpointer), `record_turn`(DB 적재), 메타에 `requires_approval`·`thread_id`(HITL 승인 게이트).
   - 주석(53행)에 "임시 연결, 시뮬/생성은 추후 추가"라고 명시.

2. **설계된 오케스트레이터** `api/assistant/` — intent 분류 → registry 디스패치(단일 패스, G5 루프 없음).
   - 계약: `core/assistant_contracts.py` — Intent(GENERATE/SIMULATE/MANAGE/RETRIEVE/ADVISE), Action(ASK/TRIGGER/ANSWER), SubagentRequest/Result, StartedEvent.
   - `wiring.build_assistant()`가 GENERATE(슬롯필링)+MANAGE(에이전틱 RAG) 등록. **라이브가 이걸 호출하지 않음.**

## ⚠️ 함정 — 관리 패리티 회귀

오케스트레이터의 `wiring._build_management_handler`는 라이브 `chat.py` 관리 경로보다 **단순**하다.
- 빠진 것: `thread_id`(멀티턴), `record_turn`(DB 적재), latency 측정.
- 그냥 갈아끼우면 **관리 채팅의 멀티턴 메모리·로깅·HITL 메타가 사라진다.** P1에서 반드시 보존.

## 액션별 SSE 매핑 (전송계층 책임)

- `result is None`(ADVISE/미등록) → 기존 **CLIO(Gemini) 스트리밍** 폴백.
- `ANSWER` → meta + message 청크 스트리밍(관리 RAG 즉답). 관리면 record_turn.
- `ASK` → message를 질문으로 스트리밍(되묻기, 잡 없음).
- `TRIGGER` → meta + `started_event`(stream_url) 방출 → 프론트가 그 SSE를 구독. message는 "시작했어요" 확인.

## 서브에이전트 출력 모양 (확인됨)

- 생성: `domain/generator/chat/slot_agent.py` — 부족=ASK(되묻기), 충족=TRIGGER + StartedEvent(`/api/generator/generations/{id}/stream`, domain=generator). 개선모드는 improve_context로 직행.
- 관리: `domain/management/assistant/agent.py` `build_management_agent` → AskRequest(question, ad_id, thread_id) → answer/citations/used_tools/suggested_action/requires_approval/thread_id.

## 인증 공백 (현재 페이즈)

- `ChatRequest`: session_id, messages, context_ad_id, context_simulation_id, improve_context. **user_id/org_id/project_id 없음**(JWT 미적용).
- 결과: SubagentRequest.user_id=None → 생성 슬롯필링이 프로젝트 단계에서 "로그인 필요" 안내로 막힘. P1은 여기까지 허용(되묻기까지 동작), 프로젝트 연결은 후속.

## 빈 구멍 — SIMULATE (P2)

- registry에 SIMULATE 미등록, intent.py에 시뮬 키워드·LLM 설명 없음.
- 시뮬은 롱러닝 잡 → TRIGGER + StartedEvent(stream_url) 패턴(생성과 동일).

## 스트림 엔드포인트 (핸드오프 타깃)

- 생성: `GET /api/generator/generations/{generation_id}/stream` (SSE, `generator_service.stream_events`).
- 시뮬: P2에서 동일 패턴 엔드포인트 필요(있으면 재사용, 없으면 추가).

## 참조 파일

- 오케스트레이터: `api/assistant/{orchestrator,intent,registry,wiring,contracts}.py`
- 계약 정본: `core/assistant_contracts.py`
- 라이브 라우터: `api/routers/chat.py`
- 생성 챗: `domain/generator/chat/slot_agent.py`, `agent.py`
- 관리 챗: `domain/management/assistant/{agent,history}.py`
