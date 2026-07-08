# 체크리스트 — 생성 기능 채팅 연결

> ⚠️ 이 문서의 1세대 설계(intent 분류 → 레지스트리 디스패치 → 슬롯필링 되묻기 루프)는
> **통합 딥에이전트로 대체됐다**(`4c3e7c8` 레거시 오케스트레이터 제거).
> 현재 아키텍처는 chat-generation-connect.context-notes.md 참고.

## 현재 구현 (완료)

- [x] 통합 딥에이전트 — `api/assistant/deep_agent_builder.py`(deepagents `create_deep_agent`),
      정책은 `prompts.py` CHAT_POLICY + 도구 docstring (별도 분류 LLM 없음)
- [x] 생성 실행 — `run_generation` @tool이 발화에서 슬롯 추출 → **gen_form 위젯**(프리필 폼).
      되묻기 루프 대신 폼이 슬롯 수집·검증을 담당, 실행은 프론트 `GenFormWidget`이
      `api.generator.start` 호출 → 진행 SSE → 완료 시 `gen_result` 위젯
- [x] 단발 개선 — `run_improvement` @tool. simulation_id(없으면 최근 완료 시뮬 자동 선택)로
      IMPROVE 프리필 조립(`api/assistant/improve_context.py`). 프리필 완비면 **즉시 실행**
      (`start_improve_generation` → gen_progress 위젯), 아니면 개선 폼 폴백
- [x] 자동 개선 루프 — `improve_ad_iteratively` @tool → `generation_loop.start_loop`
      (백그라운드 + gen_loop 위젯 신호)
- [x] 조회/조언 위임 — `ask_generator` @tool → generator ReAct 그래프
      (list_generations·get_generation_result·search_kb)
- [x] JWT — 채팅 라우터 선택적 인증(`optional_user`), created_by 전달
- [x] 승인 카드(시뮬→제너 루프) — `/api/chat/approve` action=run_generator,
      simulation_id 있으면 IMPROVE 폼 프리필

## 남은 항목

- [x] `gen_loop` 위젯 프론트 렌더러 — `GenLoopWidget` 구현(2026-07-05).
      루프 SSE 구독 → 반복별 품질점수 표시 → 완료 시 최종 시안 gen_result 위젯 연결
- [ ] 구 오케스트레이터 잔재 정리 — `api/assistant/orchestrator.py`·`wiring.py`의
      `Orchestrator`/`_try_kb_advise`는 evals에서만 참조(레거시)
