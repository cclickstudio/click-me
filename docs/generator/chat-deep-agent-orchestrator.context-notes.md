# 채팅 오케스트레이터(deep agent) — 컨텍스트 노트

> 4-4 채팅의 deep agent 전환 기록. **전환 완료**(2026-06-30, `4c3e7c8`). 이 노트는
> 최초 계획의 결정·함정이 실제로 어떻게 귀결됐는지를 남긴다.

## 최종 아키텍처 (현행)

- 진입 `POST /api/chat/complete` → `deep_agent_builder.build_unified_chat_agent(settings)`
  (deepagents `create_deep_agent`, 실패 시 LangChain `create_agent` 폴백)
- 라우팅 = CHAT_POLICY(`prompts.py`) + 각 @tool docstring. 별도 분류 LLM·키워드 분기 없음
- 도구 = `subagent_tools.build_chat_tools()` — 위임(ask_management/simulation/generator/
  general_knowledge) + 위젯(run_simulation·run_generation·run_improvement·
  improve_ad_iteratively·list_my_*·create_campaign·manage_campaign 등) + 메모리(remember/
  recall/recall_history)
- 상태 = `UnifiedChatState` — messages + per-turn 컨텍스트(session/user/org/project/
  context_ad/memory_context) + 출력 채널(widget·source·sub_meta)
- SSE = `_assemble_chat_meta`가 sub_meta(management/simulation/generator/clio)에서
  citations·위젯·카드 신호를 모아 meta로 방출

## 계획 대비 변경된 결정

| 계획 | 실제 |
|---|---|
| deepagents 서브에이전트 기능 사용 | **미사용**(`subagents=[]`) — 도메인 위임은 커스텀 @tool. 충실도·제어 우선 |
| Chat LLM = Gemini 2.0 Flash (모델 적합성 우려) | **OpenAI gpt-4o-mini** (chat_orchestrator_provider 설정) |
| state = messages+todos만, 컨텍스트는 config 주입 | per-turn 컨텍스트를 **state 채널**로(InjectedState로 도구가 읽음) |
| 관리 HITL interrupt를 deepagents task 안에서 전파 | 미채택 — **suggested_action 카드 + /api/chat/approve** 분리(계획의 폴백안) |
| 트리거 툴이 job_id/stream_url 반환(StartedEvent) | 위젯 신호로 일반화 — 실행은 프론트 위젯이, 진행은 위젯이 SSE 구독. run_improvement 즉시 실행만 백엔드가 start 후 gen_progress 카드 |

## 여전히 유효한 함정

- 백그라운드 잡은 블로킹 금지 — 루프(improve_ad_iteratively)는 start_loop 후 즉시 반환
- 공통부(`api/assistant`·`chat.py`) 동시수정 주의 — 작은 단독 PR + 사전공지
- sub_meta는 키별 덮어쓰기 병합 — 같은 턴 동일 도메인 다회 호출 시 마지막 meta만 남음

## 남은 것

- ~~gen_loop 위젯 프론트 렌더러 부재~~ → `GenLoopWidget`으로 해소(2026-07-05)
- 레거시 `Orchestrator`/`_try_kb_advise`(evals 전용) 정리
