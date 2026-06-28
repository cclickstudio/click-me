# 컨텍스트 노트 — 채팅 통합(단일 /chat 수렴, B 폐기)

> 작성 2026-06-25. 평행한 두 채팅을 통합 오케스트레이터 채팅(A) 하나로 수렴하는 작업의 배경·결정·주의점.
> 진행 체크리스트는 chat-unification.checklist.md.

## 무엇을 / 왜

- 목표 비전: 사용자가 채팅 한 곳에서 의도를 말하면 알맞은 도메인이 동작한다.
  - "광고 이미지 만들어줘" → generator 실행(생성 → 진행 → 결과).
  - "시뮬레이션 하고 싶어" → 시뮬레이터 실행.
  - "광고 관리 보고 싶어" → 매니지먼트(답변/이동).
  - 그 외 자유질문 → CLIO 어드바이저.
- 프론트 채팅 화면도 하나로 합친다(팀별 별도 화면 X). 백엔드 오케스트레이터 + 프론트 단일 화면 둘 다 단일화가 목표.

## 확정 결정 (사용자 합의)

- **A로 수렴**. 통합 채팅 `/chat`(오케스트레이터 경로) 하나로 모은다.
- **B 폐기**. `/generator-chat` 페이지 + `chat_service`(인메모리 세션·run_agent)는 평행 트랙이라 통합 시 버린다.
  단, B의 **프론트 컴포넌트(UploadPanel·InfoCard·ProgressCard)는 재활용**해 A로 이식한다(코드 자체는 살림).
- **화면은 하나, 패널은 의도별 동적**. generator 의도일 때만 업로드/정보 패널을 노출, 다른 의도면 숨김.
- **RAG(광고 생성 팁)** 은 generator 답변 분기에 KB 근거로 붙인다(별도 설계 rag-checklist.md 재활용).

## 현재 코드 사실관계 (검증됨)

### 통합 채팅 A (살릴 것)
- 진입점 `api/routers/chat.py` `POST /api/chat/complete` — SSE 스트리밍. `meta`/`token`/`started_event`/`done` 이벤트.
- 오케스트레이터 `api/assistant/orchestrator.py` `run_turn(req, project_provider)` → 의도분류 → `registry[intent].handle`.
- 등록 현황 `api/assistant/wiring.py` — `GENERATE`(generator slot_agent)·`MANAGE`(매니지먼트 RAG) 등록됨. `advise`는 CLIO 폴백(미등록). **`SIMULATE` 미등록**(시뮬 팀 합류 자리).
- 공통 계약 `api/assistant/contracts.py`(= `core/assistant_contracts`) — `SubagentRequest(messages, session_id, user_id, org_id, project_id, available_projects, context_ad_id)` / `SubagentResult(action, message, meta, started_event)` / `StartedEvent(event, job_id, stream_url, domain)`.
- generator 서브에이전트 `domain/generator/chat/slot_agent.py` `build_generation_chat_agent` — 결정론 슬롯필링(ASK/TRIGGER). 충족 시 `generator_service.start_generation` 호출 + `started_event` 반환. **업로드 키·RAG 답변 분기 없음**.
- 세션 저장 `chat.py _persist_turn` — `chat_sessions`(DB)에 누적. 복원 시 `generation` 블록으로 "결과 보기" 살림.
- 프론트 `frontend/src/app/chat/page.tsx` — SSE 파싱, 소스 배지, 인용, 세션 복원, `started_event` → 생성 진행 카드 + "생성 결과 보기 →". **업로드/정보 패널 없음**.
- 사이드바 `frontend/src/components/Sidebar.tsx` — "채팅" 메뉴가 `/chat` 가리킴(이미 노출). COMPANY 역할은 `/chat` 숨김(`COMPANY_HIDDEN_NAV`).

### generator 전용 채팅 B (폐기 대상)
- 백엔드 `domain/generator/service/chat_service.py` — `_sessions` 인메모리 dict, `create_session`/`handle_message`, `run_agent` 사용.
- 프론트 `frontend/src/app/generator-chat/page.tsx` — `/api/generator/chat/sessions/...` 호출. **업로드 패널(상품/로고)·InfoCard(3/3 필수)·ProgressCard·완료 버튼 모두 구현됨**.
- `domain/generator/chat/agent.py` `run_agent` — B 전용 경로. A에는 미연결(사실상 죽은 경로, 폐기 대상).

## 설계 — 의도별 핸드오프

| 발화 | intent | 동작 | 추가 UI |
|---|---|---|---|
| "광고 이미지 만들어줘" | generate | 슬롯 수집 → start_generation → 진행 → 완료 | 업로드 패널 + 정보 수집 패널 + 진행 카드 + 결과 보기 |
| "시뮬레이션 하고 싶어" | simulate | (시뮬 팀 합류 시) 실행 → 진행 → 결과 | 진행 카드 + 결과 보기 |
| "광고 관리 보고 싶어" | manage | RAG 답변 + 행동 제안 (이동은 열린 항목) | 인용·근거 표시 |
| 자유질문 | advise | CLIO 답변 | 소스 배지 |

핵심 원칙: **채팅창은 하나, 패널은 의도별 동적**. 마지막 assistant 메시지의 `meta.source`/intent로 우측 패널 표시를 결정.

## 작업 단계 (개요)

1. 백엔드 — slot_agent가 업로드 키(상품/로고) 수용 + 수집 슬롯을 SSE로 노출.
2. 프론트 — `/chat`에 B 컴포넌트 이식, intent=generate일 때만 노출. 업로드는 채팅에서 가능하게.
3. RAG — generator 답변 분기에 KB 붙이기.
4. 정리 — `/generator-chat` 페이지 + `chat_service`(인메모리) + `agent.run_agent` 폐기.

## 주의 / 열린 항목

- **공통부 계약 변경**: `SubagentRequest`에 업로드 키 필드 추가는 `core/assistant_contracts`(공통부) 변경 → CLAUDE.md 협업 규칙상 **사전 공지 + 시그니처 합의** 대상. 도메인 단독 PR과 분리.
- **업로드 흐름**: 현재 `/api/generator/logo`·`/api/generator/product-image`는 존재. A 채팅에서도 이 엔드포인트 재사용 가능 → 받은 key를 다음 `/api/chat/complete` 요청 바디에 실어 보내고, chat.py가 `SubagentRequest`로 전달.
- **수집 슬롯 노출 채널**: A의 SSE는 token/meta/started_event만 흘림. slot_agent가 추출한 슬롯을 `meta`나 신규 이벤트(`slots`)로 내보내야 InfoCard가 그려짐.
- **매니지먼트/시뮬 "이동" vs "답변"**: "보고 싶어"가 화면 이동이면 `started_event` 같은 **네비게이션 이벤트**가 필요. 현재 manage는 답변형. 이동 라우팅 도입 여부 미정.
- **세션 모델**: A는 무상태(매 턴 히스토리 재추출) + DB 누적. 업로드 키는 무상태와 충돌하므로 프론트가 매 요청에 key를 재전송하는 방식으로 처리(서버 세션에 안 쌓음).
- **회귀**: `/chat`은 CLIO·매니지먼트도 태우는 통합 입구 → 변경 시 manage/advise 동작 회귀 확인.
- **비목표**: 시뮬 서브에이전트 실제 구현은 시뮬 팀 몫(자리만 비워둠). improve 모드 채팅 트리거는 이번 범위 밖.
</content>
</invoke>
