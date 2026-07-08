# 채팅 오케스트레이터(deep agent) — 체크리스트

> ✅ **전환 완료** (2026-06-30, `4c3e7c8`에서 레거시 제거로 마무리). 계획 대비 달라진
> 결정은 context-notes.md의 "계획 대비 변경" 참고.

## 공통 (오케스트레이터) — 완료

- [x] `deepagents` 의존성 추가
- [x] 통합 에이전트 빌드 — `api/assistant/deep_agent_builder.py`
      `create_deep_agent(tools=build_chat_tools(...), subagents=[], ...)`
      (**deepagents 고유 서브에이전트 기능 미사용** — 커스텀 @tool 라우팅 채택)
- [x] 시스템 프롬프트 — `api/assistant/prompts.py` CHAT_POLICY (키워드 분기 0,
      도구 선택은 정책+docstring 추론)
- [x] 키워드 분류(`intent.py`·`_MGMT_KEYWORDS`) 삭제, 구 orchestrator 제거(`4c3e7c8`)
- [x] `chat.py` — 통합 에이전트 ainvoke → `_assemble_chat_meta`가 SSE meta
      (위젯·인용·카드 신호) 방출. record/feedback 유지
- [x] state — `UnifiedChatState` (messages + per-turn 컨텍스트 채널 + widget/source/sub_meta)

## 도메인별 — 완료

- [x] 시뮬레이션 — `domain/simulation/assistant/` (ReAct 그래프 + fetch_simulation_result·
      list_simulations·KOBACO 벤치마크·search_kb). `ask_simulation`/`run_simulation` 도구
- [x] 생성 — 슬롯필링 루프 폐기 → 위젯 도구(run_generation=gen_form,
      run_improvement=즉시실행/폼, improve_ad_iteratively=루프) + `ask_generator` 위임
- [x] 관리 — `ask_management` 위임(ReAct+HITL). 승인은 in-chat interrupt 대신
      **suggested_action 카드 + `/api/chat/approve`** 경로로 분리(계획의 폴백안 채택)

## 남은 항목

- [x] `gen_loop` 위젯 프론트 렌더러 — `GenLoopWidget` 구현(반복별 품질점수·완료 시
      gen_result 연결·새로고침 복원), 2026-07-05
- [ ] 레거시 잔재 정리 — `orchestrator.py`·`wiring.py`의 `Orchestrator`/`_try_kb_advise`
      (hallucination_eval 전용)
- [ ] `domain/chat/__init__.py` 설명이 실제 구현 위치(`api/assistant/`)와 어긋남 — 문서 정리
