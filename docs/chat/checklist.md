# 채팅 통합 — 체크리스트

> 단계별. P1 먼저(라이브 → 오케스트레이터). 자세한 배경은 [context-notes.md](./context-notes.md).

## P1 — 라이브 엔드포인트를 오케스트레이터로 (관리 패리티 보존)

- [ ] `chat.py`에 오케스트레이터 1회 빌드·캐시(`build_assistant(settings)`), 기존 `_is_management`/`_MGMT_KEYWORDS`/`_get_assistant` 제거.
- [ ] ChatRequest → SubagentRequest 변환(messages·session_id·context_ad_id·improve_context. user_id 등은 None).
- [ ] `orchestrator.run_turn(req)` 호출 → (intent, result) 분기.
- [ ] **관리 패리티**: wiring 관리 핸들러가 `thread_id=f"mgmt-{session_id}"`(멀티턴)·`record_turn`·latency·HITL 메타를 갖도록 보강(라이브와 동급).
- [ ] 액션→SSE 매핑: None→CLIO, ANSWER→meta+청크, ASK→질문 청크, TRIGGER→meta+started_event+확인.
- [ ] CLIO 폴백 경로(Gemini 스트리밍) 그대로 유지.
- [ ] 회귀 점검: 관리 질문 멀티턴·인용·승인게이트 동작, CLIO 일반질문 동작, "광고 만들어줘" → 슬롯 되묻기(ASK) 동작.
- [ ] 테스트: 라우터 단위테스트(관리 ANSWER·생성 ASK·advise 폴백 각 1개). `ruff` + `pytest tests/` 통과.
- [ ] 프론트 확인 사항 메모: `/chat` 페이지가 `started_event`(stream_url)를 받아 생성 진행 SSE를 구독하는지 — 백엔드가 방출하는 이벤트 포맷 합의.

## P2 — 핵심 흐름: 시뮬 → 결과 → 개선 (북극성)

> [context-notes.md](./context-notes.md)의 "목표 사용자 흐름"을 실제로 동작시키는 단계.

### 2a. 채팅 이미지 첨부 (시뮬·생성 공통 선행)

- [ ] 채팅 메시지에 이미지 첨부 경로 신설 — 업로드 → s3_key 확보 → SubagentRequest로 전달.
- [ ] 프론트 `/chat`: 이미지 첨부 UI(시뮬=광고 이미지 **필수**, 생성=상품/로고 **선택**).
- [x] ✅ 결정: 시뮬은 광고 이미지 **필수**(없으면 무조건 되묻기). 그 이미지가 개선모드 참고자료로 재사용됨.

### 2b. SIMULATE 서브에이전트

- [ ] `domain/simulation`에 채팅 핸들러 어댑터(SubagentRequest → 시뮬 트리거) — 롱러닝 → TRIGGER + StartedEvent(stream_url).
- [ ] 이미지 없으면 **ASK("광고 이미지를 넣어주세요")**, 있으면 **TRIGGER**.
- [ ] 시뮬 SSE 스트림 엔드포인트 확인/추가(`/api/simulation/.../stream`).
- [ ] `wiring`에 `Intent.SIMULATE` 등록.
- [ ] `intent.py`: 시뮬 키워드 + LLM 분류 설명("simulate: 광고 반응 예측/시뮬레이션 요청") 추가.
- [ ] 테스트: 이미지 없는 시뮬 요청 → ASK / 이미지 있는 요청 → TRIGGER.

### 2c. 시뮬 → 생성(개선) 바통터치

- [ ] 시뮬에 올린 광고 이미지 s3_key를 흐름 내내 보관 → 개선 때 `improve_context.s3_key`로 그대로 전달(같은 이미지 일관 추적).
- [ ] 시뮬 결과(요약 + 광고 이미지 s3_key)를 생성 담당 `improve_context`(s3_key·simulation_summary·product_name) 포맷으로 변환.
- [x] ✅ 결정: 결과 직후 "개선할까요?"를 **자동 제안**(AI 비서 선제성). 실행은 사용자 수락 시.
- [ ] 결과 직후 "개선할까요?" 자동 제안 → 사용자가 수락하면 GENERATE(개선모드)로 라우팅 → 개선 이미지 TRIGGER.
- [ ] 테스트: 시뮬 결과 → 개선 수락 → 생성 IMPROVE TRIGGER(기존 slot_agent improve 분기 재사용).

## P3 — 마감 (멀티턴·관측·일관성·관리 연결·AI 비서)

- [ ] 관리(management) 흐름을 교통정리에 연결(이미 만들어진 담당 — 붙이기만).
- [ ] **롱텀 메모리(LTM)** — 관리 spec의 STM/LTM 설계(구현 대기)를 통합 채팅용으로 일반화(도메인 중립). 세션 넘어 사용자 기억 → AI 비서 선제성. 상세는 별도 spec.
- [ ] RETRIEVE(교차 검색) 핸들러 검토.
- [ ] 세션/히스토리 통합 — 관리의 checkpointer·history를 공통 패턴으로 일반화.
- [ ] meta/인용 스키마 도메인 간 일관화(프론트 표시 단일화).
- [ ] 프로젝트 컨텍스트 연결(인증 도입 시 user_id→available_projects provider).
