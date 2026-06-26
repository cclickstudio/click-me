# 챗 숏텀 메모리 — LangGraph state(체크포인터) 기반 컨텍스트 유지

> 작성 2026-06-26 · 도메인 `domain/chat` · 상태 설계 확정(구현 전)

## 1. 배경 / 문제

챗 컨시어지의 서브에이전트(시뮬·생성·매니지먼트)는 **무상태**다. 슈퍼바이저가
위임할 때 `_last_user_text(...)` 즉 **현재 메시지 한 줄만** 넘긴다([nodes.py:168](../../../backend/domain/chat/graph/nodes.py)).
그래서 다중턴 슬롯필링이 끊긴다.

```
턴1  사용자: "이 광고 시뮬 돌려줘"   →  에이전트: "표본 몇 명으로 할까요? (기본 20)"
턴2  사용자: "50명"                  →  에이전트: 백지 상태 — "50명"이 무엇의 답인지 모름
```

목표는 **"표본 몇 명?" → "50명" → 실행** 이 자연스럽게 이어지는 진짜 되묻기다.

## 2. 핵심 원칙 — "숏텀 메모리 = 체크포인터 state, `chat_messages`는 표시 전용"

턴을 넘겨 상태를 유지하려면(턴1·턴2는 별개 HTTP 요청·별개 그래프 호출) 어딘가에
저장이 필요하다. 두 요청은 프로세스 메모리를 공유하지 않는다. 그 저장·복원을
담당하는 것이 **체크포인터**이고, 이것이 곧 "LangGraph state를 thread_id 기준으로
주고받는" 메커니즘이다. 따라서 별도의 손수 짠 DB 조회를 메모리 소스로 두지 않고
**체크포인터가 누적한 `state["messages"]`를 단일 메모리 소스**로 삼는다.

| 계층 | 무엇 | 누가 보나 | 용도 |
| --- | --- | --- | --- |
| 턴 내 state | `ChatState` 인메모리 | 노드 | 그래프 실행 |
| **체크포인터 state** | `state["messages"]`·`context_ids` 자동 누적(thread=session) | 슈퍼바이저·라우터·(신규)서브에이전트 | **숏텀 메모리** |
| `chat_messages` 테이블 | 정규화 행(role·route·meta·시각) | UI·세션목록·리로드 | **표시·이력 전용** |

체크포인터 배선은 이미 존재한다 — 실모드 `AsyncPostgresSaver`(Postgres 영속),
mock/테스트 `MemorySaver`(RAM) ([wiring.py:51-66](../../../backend/domain/chat/wiring.py)).
`ChatState.messages`는 `add_messages` 리듀서라 같은 세션에서 턴을 넘어
`[H1, A1, H2, A2, …]`로 **이미 자동 누적**된다. 즉 슈퍼바이저·라우터 레벨의 숏텀
메모리는 이미 state 기반으로 동작 중이고, 빠진 것은 **서브에이전트까지 전달**뿐이다.

## 3. 설계 — A / B / C

### A. 히스토리 → 서브에이전트 (핵심)

- **계약**: `SubAgentRequest`에 `history: list[dict]`(`[{role, content}]`) 추가.
- **delegate 노드**: 메모리 소스를 `state["messages"]`로. 마지막 메시지(현재
  HumanMessage)는 `question`으로 따로 가므로 제외하고, 최근 N개로 윈도잉한 뒤
  LangChain 메시지 → `{role, content}` dict로 변환해 `SubAgentRequest.history`에 싣는다.
  (계약은 직렬화 가능해야 하므로 LC 객체가 아닌 dict로 교환.)
- **서브에이전트 주입(프리앰블, 어댑터 계층)**: ReAct 내부를 건드리지 않고 **어댑터에서
  히스토리를 질문 앞에 프리앰블로 붙인다** — `q = history_to_preamble(history) + question`을
  기존 `agent(q, context_ids)`/`AskRequest(question=q)`에 전달. 사용자가 처음 말한
  "최근 대화를 User 메시지 앞에 붙여" 방식 그대로다. 적용 대상 — `simulation_subagent`·
  `generator_subagent`·`management_subagent`(셋 다 chat 도메인 어댑터, **타 도메인 내부
  무수정** → 협업 규칙 준수). 히스토리가 비면 프리앰블=""이라 1턴 동작 불변.
- **프롬프트 전환(단일턴 → 되묻기)**: `sim_agent`/`gen_agent`의 `_SYSTEM`을 "필수 슬롯이
  없고 [이전 대화]에 아직 물어본 적 없으면 **한 번만** 되묻는다. [이전 대화]에 이미 그
  질문이 있고 이번 메시지가 그 답(또는 '그냥/기본')이면 되묻지 말고 실행한다"로.

### B. 라우팅 연속성 — "50명"을 다시 같은 에이전트로 (B1, 프롬프트 규칙)

라우터(`decide_route`)는 이미 `state["messages"]`(전체 대화)를 받는다. 새 상태·
플래그 없이 정책 프롬프트에 규칙 한 줄을 추가한다.

> 직전 어시스턴트 메시지가 특정 에이전트의 되묻기(추가 질문)이고, 이번 사용자
> 메시지가 그에 대한 짧은 답이면 **같은 에이전트로** 라우팅한다.

라이브에서 오라우팅이 관측되면 후속으로 B2(확정적)로 승급한다 — `SubAgentResult.awaiting_input`
→ 어시스턴트 meta 영속 → `load_context`가 읽어 `continue_route` 세팅 → 슈퍼바이저가
LLM 라우팅을 무시하고 강제. (이번 범위에는 미포함, 업그레이드 경로만 명시.)

### C. 광고 컨텍스트(ad_id·이미지) 턴2 생존 — `context_ids` merge 리듀서

프론트가 전송 직후 첨부를 비우므로([page.tsx:202](../../../frontend/src/app/(app)/chat/page.tsx))
턴2 요청은 `context_ad_id: null`로 도착한다. 현재 `context_ids`는 plain 채널이라
턴2 입력이 체크포인트된 값을 통째로 덮어써 ad_id가 사라진다.

`ChatState.context_ids`를 merge 리듀서로 바꾼다 — **옛 값 유지 + 새 non-null만 덮어쓰기**.

```python
def _merge_context(old: dict | None, new: dict | None) -> dict:
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if v is not None:
            merged[k] = v
    return merged
# ChatState.context_ids: Annotated[dict, _merge_context]
```

이로써 턴2의 null이 ad_id를 못 지운다. **프론트 수정 불필요.** 광고 교체는 새
non-null id가 덮어쓰므로 정상 동작하고, 완전 새 대화는 새 session_id=새 thread =
빈 체크포인트라 깨끗이 시작된다.

## 4. 메모리 소스 통일 — `short_term` DB 조회 은퇴

`load_context`가 매 턴 `repo.get_messages(limit=20)`로 채우던 `short_term`을
**`state["messages"]` 윈도우에서 파생**하도록 바꾼다(DB 라운드트립 제거). general/CLIO
라우트의 `short_term` 소비부([nodes.py:233](../../../backend/domain/chat/graph/nodes.py))는
그대로 동작한다. `chat_messages` 쓰기(`_persist_user`/`_persist_assistant`)는 표시·
세션목록·리로드용으로 **유지**한다.

윈도우 크기 N은 **챗 도메인 로컬 상수**(`nodes.py`의 `_HISTORY_WINDOW = 20` 메시지 =
10턴)로 두고 **읽을 때 슬라이스**한다. core/config.py(공통부) 변경을 피해 협업 규칙을
지킨다 — 추후 튜닝 필요가 생기면 그때 설정값으로 승격. 저장소 자체 prune은 후속
`RemoveMessage` 과제로 분리.

## 5. 데이터 흐름 (턴2 "50명" 기준)

```
요청(50명, ad_id=null)
  └ stream(): initial.messages=[Human("50명")], context_ids={ad_id:null,…}
      └ 체크포인터 복원 → messages=[…,A("표본 몇명?")] + Human("50명")
                          context_ids merge → ad_id=턴1값 유지
  └ load_context: short_term = window(state.messages)
  └ supervisor/decide_route: 직전 A가 시뮬 되묻기 + 짧은 답 → route=simulation (B1)
  └ delegate: history = window(messages[:-1])→dict, context_ids(ad_id 생존) 동봉
      └ sim subagent(어댑터): q = preamble(history) + "50명" → ReAct가 "50명"=표본 답 인식
                       + ad_image_url(생존) → start_simulation(sample_size=50) 실행
  └ synthesize → AIMessage 누적 → chat_messages 영속(표시용)
```

## 6. 영향 파일

**수정**
- `domain/chat/contracts/agent_io.py` — `SubAgentRequest.history` 추가.
- `domain/chat/graph/state.py` — `context_ids`에 `_merge_context` 리듀서.
- `domain/chat/graph/nodes.py` — `load_context`(short_term=state 파생), `delegate`(history 동봉),
  `_messages_to_history` 윈도우 헬퍼, `_HISTORY_WINDOW` 로컬 상수.
- `domain/chat/graph/supervisor.py` — `_ROUTING_SYSTEM`에 B1 연속성 규칙(프롬프트만).
- `domain/chat/adapters/sim_agent.py`·`gen_agent.py` — `_SYSTEM` 되묻기 프롬프트(ReAct 내부 무변경).
- `domain/chat/adapters/simulation_subagent.py`·`generator_subagent.py`·`management_subagent.py`
  — 어댑터에서 히스토리 프리앰블을 질문 앞에 주입.

**신규**
- `domain/chat/adapters/history.py` — `history_to_preamble(history)` 포매터(3개 어댑터 공유).

**참조/무변경**: `wiring.py`(체크포인터 이미 배선), `core/`(공통부 미변경), `domain/management/*`
(타 팀 — 무수정), `chat_messages` 영속부, 프론트(C가 백엔드 해결).

## 7. 비범위 (YAGNI)

- **롱텀 메모리(LTM)** — `MemoryStore.recall`/`long_term` 스텁 유지, 켜기는 후속.
- **저장소 prune(`RemoveMessage`)** — 읽기 슬라이스로 충분, 토큰 압박 시 후속.
- **B2 확정적 라우팅** — B1로 시작, 오라우팅 관측 시 승급.
- **세션 요약(summary)** — `update_summary` 포트는 있으나 이번 범위 밖.

## 8. 엣지케이스 / caveat

- **mock=MemorySaver(RAM)** — 로컬 mock 재시작 시 메모리 소실(개발 전용). 실모드는
  Postgres 영속이라 재시작·리로드에도 thread_id로 복원. 멀티워커 확장 시 MemorySaver는
  비공유 — 단일 EC2 단일 프로세스면 무관.
- **현재 턴 중복 방지** — 서브에이전트엔 `history = messages[:-1]` + `question`(현재)으로
  분리 전달해 마지막 사용자 발화가 두 번 들어가지 않게 한다.
- **merge 리듀서는 unset 불가** — null로 컨텍스트를 비울 수 없다(새 non-null로 교체만
  가능). 새 대화는 새 세션으로 시작하므로 수용 가능.
- **윈도우 경계** — N이 작으면 오래된 슬롯 질문이 윈도우 밖으로 밀려 되묻기 단절 가능.
  기본 20(10턴)이면 슬롯필링 1~2턴엔 충분.

## 9. 검증 계획

- **단위(hermetic, 실 DB 무의존)**
  - `_merge_context`: 옛 값 유지·새 non-null 덮어쓰기·null 무시.
  - `_messages_to_history`: LC→dict 변환·role 매핑·윈도우 슬라이스·현재 턴 제외.
  - `delegate`가 `SubAgentRequest.history`를 채우는지(가짜 서브에이전트로 캡처).
  - `history_to_preamble`: 빈 히스토리→"", 있으면 `[이전 대화]`·`[현재 질문]` 구획 포함.
  - 어댑터가 프리앰블을 질문 앞에 붙여 agent에 넘기는지(가짜 agent로 캡처).
  - `decide_route` B1 규칙은 LLM 전용 → 라이브 검증(hermetic 불가).
- **라이브(실 Claude, 시뮬 실행은 가짜 서비스로 가로채 비용 0)**
  - 턴1 "이 광고 시뮬 돌려줘"(표본 미지정) → 되묻기 1회.
  - 턴2 "50명" → 같은 에이전트 라우팅 + `start_simulation(sample_size=50)` + ad_id 생존.
- `cd backend && uv run ruff format . && uv run ruff check .` + `uv run pytest tests/chat -q`.

## 10. 리스크

- **B1 오라우팅** — 짧은 답("50명")이 general로 샐 가능(LLM 판단). 완화: 라우터가
  전체 대화를 보므로 규칙으로 충분할 확률 높음. 실패 시 B2 승급.
- **토큰 증가** — 매 서브에이전트 호출에 히스토리 N개 프리펜드. 완화: 윈도우 슬라이스.
- **merge 리듀서 부작용** — 다른 context 키(simulation_id 등)도 sticky해짐. 의도된 동작이나,
  엉뚱한 잔존이 보이면 키별 화이트리스트로 좁힌다.
