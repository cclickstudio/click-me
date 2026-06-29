# 채팅 오케스트레이터(deep agent) — 컨텍스트 노트

> 4-4 채팅을 deep agent 오케스트레이터로 전환하는 작업의 배경·결정·함정 기록.
> 작업줄기 소유: 공통(api/assistant) + 각 도메인 chat 표면. 협업규칙상 공통부는 작은 단독 PR.

## 확정된 결정 (사용자)

- **오케스트레이터 = deep agent** (`deepagents`, 자율 계획+위임 루프). 기존 단일패스 분류 디스패치를 대체.
- **state 최소** — `messages + todos`만. 세션 컨텍스트는 state가 아니라 config 주입.
- **상태확인 = 문맥파악** — 명시적 상태머신/슬롯 추적 금지. 대화·툴결과를 보고 추론.
- **키워드 의도파악 금지** — `intent.py` 키워드 분류, `chat.py` `_MGMT_KEYWORDS`/`_is_management` 폐기.
- **통합 경계 = 혼합** — 읽기·단발 액션은 `@tool`, 해석/다단계(시뮬분석·관리RAG)는 서브에이전트.

## 현재 코드 지도 (재사용/폐기)

재사용:
- `core/assistant_contracts.py` — `SubagentRequest/Result`, `Action(ASK/TRIGGER/ANSWER)`, `StartedEvent`. 의존방향 정상(domain→core, api→core).
- `api/assistant/wiring.py` — composition root. deep agent 조립도 여기서.
- `domain/management/assistant/agent.py` + `graph.py` — ReAct + pgvector KB + HITL interrupt. 이미 서브에이전트.
- `domain/generator/chat/slot_agent.py`의 `StartedEvent` 핸드오프 패턴.

폐기/대체:
- `api/assistant/intent.py` 키워드 분류 → 삭제 (deep agent가 추론으로 흡수).
- `api/assistant/orchestrator.py` 단일패스(G5 "루프 없음") → deep agent 루프로 교체.
- `api/routers/chat.py` `_MGMT_KEYWORDS`/`_is_management` → 삭제.
- generator 결정론 슬롯필링 루프 → `start_generation` 툴 하나로 단순화(파라미터 수집은 deep agent 대화가 담당).

## 도메인 납품 계약 (모든 팀 동일)

각 팀은 `domain/<ctx>/chat/`에서 다음을 노출하고 `wiring.py`가 조립한다.
- `build_<ctx>_tools(settings) -> list[BaseTool]` — 각 툴에 한 줄 description + "언제 쓰나".
- (해석/다단계인 경우) 서브에이전트 스펙 또는 컴파일 그래프.
- 타 도메인 내부 직접 import 금지 — 교환은 contracts/툴 표면으로만.

## 함정 / 리스크

- **모델 적합성** — Chat LLM 결정은 Gemini 2.0 Flash. deep agent의 계획+위임은 Flash엔 부담 → 오위임/루프 위험. 오케스트레이터만 상위 모델 검토.
- **G5 반전** — 최상위 루프 허용. 재귀 한도·todo 종료조건으로 무한루프 방지 필수.
- **백그라운드 잡 핸드오프** — generator/simulation 트리거 툴은 즉시 `job_id/stream_url` 반환(블로킹 금지). 부수효과(`StartedEvent`)를 SSE로 표면화.
- **관리 HITL** — `interrupt()` 기반 승인이 deepagents `task` 안에서 전파되는지 미검증. 안 되면 승인은 기존 approval 화면으로 분리(인-챗 interrupt 회피).
- **프론트 SSE** — `frontend/src/app/chat/page.tsx`는 현재 `meta/token/done`만 처리. `started_event` 처리 추가 필요.
- **공통부 동시수정** — `api/assistant`·`core/assistant_contracts`·`chat.py`·`api/main.py`는 작은 단독 PR + 사전공지.
