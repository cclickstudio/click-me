# 컨텍스트 노트 — 생성 기능 채팅 연결 (feat/chat-yohan2)

> 작업 목표. 채팅에서 "광고 만들어줘"를 하면 부족한 정보를 되묻고(결정론 슬롯필링), 다 모이면 `start_generation`을 트리거하고, started_event로 생성 SSE 스트림에 핸드오프한다. 적합안(문서 A) 기준.

## 확정 결정 (사용자 합의)
- **범위** 공통 계약 + 레지스트리부터 정식 구축, 생성을 첫 등록.
- **project_id** 에이전트가 사용자 프로젝트를 조회해 되물어 선택.
- **진행 표시** started_event 핸드오프 — 채팅은 시작 이벤트만, 프론트가 기존 생성 SSE 구독.
- **유저/프로젝트** 채팅에 JWT 연동 — 프론트가 토큰 첨부 + 백엔드 채팅에 선택적 인증.
- **슬롯 추출 모델** Gemini(`langchain_google_genai`). 키 없으면 폴백(되묻기/스텁).
- **created_by** JWT 유저 있으면 `user.id`, 없으면 None.

## 현 코드 사실 (검증됨)
- `chat.py`는 키워드로 management만 라우팅, 나머지 CLIO(raw genai, 미추적). → 레지스트리로 교체.
- management `AskRequest/AskResult`가 공통 계약 템플릿. 진입점 `build_management_agent(settings) -> ask`.
- `generator_service.start_generation(GenerationCreateRequest, created_by) -> id`, `stream_events(id)`. (같은 도메인 → 슬롯 에이전트가 직접 호출 가능)
- CREATE 필수 슬롯: `product_name·product_description·target_audience` + `project_id`(저장). 기본값: campaign_objective=conversion, format=single.
- `get_current_user`는 **실 JWT 검증**(스텁 아님). 미인증이면 401 → 그래서 채팅은 **선택적 인증**(없어도 advise는 동작).
- 프론트 `api.ts`는 `getToken()`으로 Bearer 첨부. `chat/page.tsx`의 fetch만 토큰 누락 → 한 줄 추가.
- 프로젝트는 org/team/role 스코프. 챗 픽커는 **org 단위(id,name)** 로 단순화(team-level 필터 생략).

## 설계 (적합안)
```
chat.py(router, 선택적 user + db)
  → orchestrator.run_turn(SubagentRequest, project_provider)
       ├ classify_intent  (Gemini 1콜, 키없으면 키워드 폴백)  ← 계측
       └ registry[intent].handle(req) -> SubagentResult(action, message, started_event)
            generate: domain/generator/chat (슬롯필링 결정론 루프)
            manage  : domain/management/assistant (기존 에이전틱 RAG 어댑터)
            advise  : CLIO (Gemini 계측)
```
- 공통 계약/오케스트레이터 = `backend/api/assistant/` (전송·조합 계층).
- 생성 서브에이전트 = `backend/domain/generator/chat/` (generator 도메인 소유, 빈 디렉터리 활용).
- wiring(api/assistant/wiring.py)이 composition root — 도메인 build 함수를 레지스트리에 등록.

## 핵심 계약
- `SubagentRequest(messages, session_id, user_id, org_id, project_id, available_projects)`
- `SubagentResult(action: ask|trigger|answer, message, meta, started_event)`
- `StartedEvent(event, job_id, stream_url, domain)`
- 생성 트리거 시 `started_event = {event:"generation_started", job_id:gen_id, stream_url:/api/generator/generations/{id}/stream, domain:"generator"}`.

## 슬롯필링 루프 (결정론)
1. 히스토리에서 슬롯 추출(LLM). 2. 프로젝트 미정 & available_projects 있으면 목록 제시(ask). 3. 필수 슬롯 부족 → 해당 슬롯 되묻기(ask). 4. 전부 충족 → start_generation → trigger + started_event. 종료조건 = 슬롯 충족.

## 비목표 / 주의
- 채팅 DB 영속화 X(무상태, 매 턴 히스토리 재추출).
- improve 모드는 이번 범위 아님(create만).
- team-level 프로젝트 가시성 정밀필터는 생략(org 단위). 추후 정교화.
- `api/main.py` 라우터 등록 변경 없음(chat 라우터는 이미 등록됨) — append-only 규칙 영향 없음.
