# 체크리스트 — 생성 기능 채팅 연결 (feat/chat-yohan2)

## 백엔드 — 공통(오케스트레이터)
- [ ] `api/assistant/contracts.py` — SubagentRequest/Result, Action enum, StartedEvent, ProjectRef, Intent
- [ ] `api/assistant/registry.py` — dict 레지스트리(register/get)
- [ ] `api/assistant/intent.py` — classify_intent (Gemini 계측 + 키워드 폴백)
- [ ] `api/assistant/orchestrator.py` — run_turn(req, project_provider) → SubagentResult
- [ ] `api/assistant/wiring.py` — build_assistant(): generate/manage/advise 핸들러 등록

## 백엔드 — 생성 서브에이전트 (generator 도메인)
- [ ] `domain/generator/chat/contracts.py` — GenerationSlots
- [ ] `domain/generator/chat/slot_agent.py` — build_generation_chat_agent(settings) → handle(req)
  - [ ] 슬롯 추출(LLM, 폴백)
  - [ ] 프로젝트 되묻기(available_projects)
  - [ ] 필수 슬롯 되묻기
  - [ ] 충족 시 start_generation 트리거 + started_event

## 백엔드 — 라우터
- [ ] `core/auth.py` 또는 deps — 선택적 인증(`get_current_user_optional`) 추가
- [ ] `api/routers/chat.py` — 레지스트리 사용으로 리팩토링, 선택적 user+db, project_provider 주입
- [ ] CLIO(advise) Gemini 계측 전환(D1) — 선택(여유되면)

## 프론트
- [ ] `chat/page.tsx` — 채팅 fetch에 Authorization 토큰 첨부
- [ ] `chat/page.tsx` — started_event 수신 → 진행 카드 + 생성 SSE 구독

## 테스트
- [ ] 슬롯 추출/되묻기/트리거 단위 테스트 (LLM 스텁)
- [ ] 레지스트리/분류기 단위 테스트
- [ ] `uv run ruff format . && uv run ruff check . --fix`
- [ ] `uv run pytest tests/ -v` (관련 범위)

## 완료 기준
- 채팅에서 "○○ 광고 만들어줘" → 상품/타깃 되묻기 → 프로젝트 선택 → 생성 시작 + 스트림 핸드오프.
- 기존 management/CLIO 동작 회귀 없음.
- 슬롯 추출·분류 LLM이 LangSmith에 기록(계측).
