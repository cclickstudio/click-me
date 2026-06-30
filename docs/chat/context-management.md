# 챗 컨텍스트 관리 — 전(前) vs 현(現)

> 챗 오케스트레이터(4-4)가 대화 맥락을 어떻게 들고 가는지. 2026-06-26 숏텀 메모리(state 기반) 도입 기준.

## 한눈에

| 축 | 전(前) | 현(現) |
| --- | --- | --- |
| 숏텀 메모리 소스 | 슈퍼바이저는 체크포인터, **서브에이전트는 없음** | **체크포인터 `state["messages"]` 단일 소스** |
| 서브에이전트가 보는 것 | 현재 메시지 **한 줄**(`_last_user_text`) | 현재 질문 + **최근 대화 프리앰블** |
| 다중턴 슬롯필링 | 불가(무상태) | 가능("표본 몇 명?" → "50명" → 실행) |
| short_term | DB(`chat_messages`)에서 매 턴 조회 | `state["messages"]`에서 파생(DB 조회 은퇴) |
| 광고 컨텍스트(ad_id·이미지) | plain 채널 — 턴2 null이 덮어써 소실 | **merge 리듀서로 턴 넘겨 생존** |
| `chat_messages` 테이블 | 메모리 겸 표시 | **표시·세션목록·리로드 전용** |
| 롱텀(LTM) | 스텁만 | 스텁만(보류) |

## 메커니즘 3계층 (변함없는 토대)

1. **턴 내 state** — `ChatState`(TypedDict) 인메모리. 노드들이 한 턴 동안 주고받음.
2. **체크포인터 state** — `AsyncPostgresSaver`(실)/`MemorySaver`(mock)가 `thread_id=session_id` 기준으로 state를 자동 저장·복원. `messages`는 `add_messages` 리듀서라 **턴을 넘어 `[H1,A1,H2,A2,…]`로 누적**. → "state로 주고받기"의 실제 구현체. 턴1·턴2는 별개 HTTP 요청이라 이 영속이 없으면 맥락이 끊긴다.
3. **`chat_messages` 테이블** — `_persist_user`/`_persist_assistant`가 매 턴 정규화 행으로 저장. UI 표시·세션 목록·리로드용.

## 전(前) — 어떻게였나

- **슈퍼바이저/라우터**는 체크포인터 덕에 이미 전체 대화를 봤다(`decide_route(state["messages"])`).
- **서브에이전트(시뮬·생성·관리)는 무상태**였다. `delegate`가 `SubAgentRequest(question=_last_user_text(...))` — **현재 메시지 한 줄만** 넘기고 `history` 필드 자체가 없었다. 그래서 "표본 몇 명?"이라 되물어도 다음 턴에 "50명"이 무엇의 답인지 몰랐다.
- `load_context`가 `repo.get_messages(session_id, limit=20)`로 DB에서 `short_term`을 읽어 state에 실었고, 이는 **general/CLIO 라우트에서만** 쓰였다.
- 광고 컨텍스트(`ad_id`/이미지)는 매 턴 프론트가 보내는 `context_ids`로만 들어왔고, `context_ids`가 plain 채널이라 **턴2에 프론트가 첨부를 비우면(`page.tsx` `setAttached(null)`) null이 이전 값을 통째로 덮어써 소실**됐다.

## 현(現) — 어떻게 바뀌었나

원칙: **숏텀 메모리 = 체크포인터 `state["messages"]`(단일 소스), `chat_messages`는 표시 전용.** 새 DB 조회를 만들지 않고 이미 누적되는 state를 서브에이전트까지 흘린다.

- **A. 히스토리 → 서브에이전트.** `SubAgentRequest.history` 추가. `delegate`가 `_messages_to_history(state["messages"][:-1])`(현재 턴 제외, 최근 `_HISTORY_WINDOW=20`개)로 채우고, 각 어댑터(`simulation_subagent`·`generator_subagent`·`management_subagent`)가 `history_to_preamble(history)`로 **질문 앞에 `[이전 대화]…[현재 질문]` 프리앰블**을 붙여 기존 ReAct/ask에 넘긴다. 타 도메인 내부는 무수정.
- **B1. 라우팅 연속성.** `_ROUTING_SYSTEM`에 규칙 — 직전 어시스턴트가 되물음이고 이번이 그 짧은 답이면 같은 위임처로(LLM 판단).
- **C. 광고 컨텍스트 생존.** `ChatState.context_ids`를 `Annotated[dict, _merge_context]`로 — 옛 값 유지 + 새 non-null만 덮어쓰기. 턴2의 null이 ad_id를 못 지운다(프론트 무수정).
- **short_term 통일.** `load_context`가 DB 조회 대신 `_messages_to_history(state["messages"])`로 파생. general/CLIO 동작 유지.
- **되묻기.** `sim_agent`/`gen_agent` `_SYSTEM`이 단일턴→되묻기(슬롯 없고 [이전 대화]에서 안 물었으면 1회 질문, 답이 있으면 실행).

## 데이터 흐름 (턴2 "50명" 기준)

```
요청(50명, ad_id=null)
 └ stream(): messages=[Human("50명")], context_ids={ad_id:null}
     └ 체크포인터 복원 → messages=[…,A("표본 몇명?")]+Human("50명")
                        context_ids merge → ad_id=턴1값 유지
 └ load_context: short_term = _messages_to_history(messages)
 └ supervisor: 직전 A가 시뮬 되물음 + 짧은 답 → simulation (B1)
 └ delegate: history=_messages_to_history(messages[:-1]), context_ids(ad_id 생존) 동봉
     └ sim 어댑터: q = history_to_preamble(history)+"50명" → ReAct가 "50명"=표본 인식
                   + ad_image_url(생존) → start_simulation(sample_size=50)
 └ synthesize → AIMessage 누적 → chat_messages 영속(표시용)
```

## 관련 파일

- 상태/리듀서 `domain/chat/graph/state.py` · 노드/헬퍼 `graph/nodes.py`(`_messages_to_history`·`_HISTORY_WINDOW`·`delegate`·`load_context`) · 라우터 `graph/supervisor.py` · 프리앰블 `adapters/history.py` · 어댑터 `adapters/{simulation,generator,management}_subagent.py` · 계약 `contracts/agent_io.py`(`SubAgentRequest.history`) · 체크포인터 배선 `wiring.py`.

## 알려진 한계·이슈

- **CLIO general 경로 현재 턴 중복(버그).** `adapters/clio.py:_contents`가 history를 깐 뒤 현재 질문을 또 append하는데, `short_term`이 이미 현재 턴을 포함 → 현재 user 턴 중복. general로 (오)라우팅된 질의에서 직전 답을 되풀이하는 증상과 연관. 수정 시 general 경로엔 현재 턴 제외 히스토리를 전달해야 함.
- **mock = `MemorySaver`(RAM)** — 로컬 mock 재시작 시 메모리 소실(개발 전용). 실모드(Postgres)는 thread_id로 복원.
- **merge 리듀서는 unset 불가** — 세션 내 컨텍스트는 sticky(새 대화=새 session_id로만 초기화).
- **B1은 LLM 판단** — 확정 라우팅(B2)·LTM 회상·저장소 prune·세션요약은 보류.
