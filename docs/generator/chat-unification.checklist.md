# 체크리스트 — 채팅 통합(A 수렴, B 폐기)

> 단일 /chat 화면에서 의도분류 → 도메인 핸드오프. generator를 업로드·정보패널·RAG까지 통합 채팅에 완성.
> 배경·결정은 chat-unification.context-notes.md.

## ① 백엔드 — 업로드 키 수용 (공통부, 사전 공지 필요)

- [ ] `SubagentRequest`(`core/assistant_contracts`)에 업로드 키 필드 추가 — `brand_logo_s3_key`, `product_image_temp_key` (선택)
  - [ ] ⚠️ 공통부 계약 변경 → 팀 사전 공지 + 단독 PR로 분리
- [ ] `core/schemas.py` `ChatRequest`에 업로드 키 필드 추가(프론트 → 라우터 전달용)
- [ ] `api/routers/chat.py` — body의 업로드 키를 `SubagentRequest`로 주입
- [ ] `domain/generator/chat/slot_agent.py` — 업로드 키를 `GenerationCreateRequest`(brand_logo_s3_key·product_image_temp_key)에 실어 컴포즈 모드 생성

## ② 백엔드 — 수집 슬롯 SSE 노출

- [ ] slot_agent가 이번 턴 추출 슬롯을 `SubagentResult.meta`(또는 신규 `slots` 키)에 포함
- [ ] `chat.py` generate 응답에 슬롯 상태 SSE로 흘리기 (InfoCard 갱신용)
- [ ] 필수 3슬롯(product_name·product_description·target_audience) 충족 여부도 함께

## ③ 프론트 — /chat에 generator 패널 이식

- [ ] B의 `UploadPanel`·`InfoCard`·`ProgressCard` 컴포넌트 추출(공용화 or chat 내부 이동)
- [ ] `chat/page.tsx` — intent=generate(meta.source=generator)일 때만 우측 패널 노출, 그 외 숨김
- [ ] 업로드: `/api/generator/logo`·`/api/generator/product-image` 재사용 → 받은 key를 다음 `/api/chat/complete` 바디에 첨부
- [ ] 수집 슬롯 SSE 수신 → InfoCard 갱신
- [ ] 생성 진행/완료/결과 보기는 기존 `started_event` + `subscribeGeneration` 흐름 재사용(확인)

## ④ RAG — 광고 생성 팁 (rag-checklist.md 재활용)

- [ ] generator 답변 분기 추가 — "질문이면 KB 답변, 정보면 슬롯" (슬롯 비었고 질문형일 때)
- [ ] KB 인메모리 retriever(`domain/generator/chat/kb_retriever.py`) — 코사인 top-k, `{source,title,chunk,score}`
- [ ] 답변 `meta.citations`에 출처 실어 프론트 인용 표시(매니지먼트 형태 호환)

## ⑤ 정리 — B 폐기

- [ ] `frontend/src/app/generator-chat/page.tsx` 삭제
- [ ] `domain/generator/service/chat_service.py`(인메모리 세션) 삭제 + 라우터 참조 제거
- [ ] `domain/generator/chat/agent.py` `run_agent`(죽은 경로) 정리
- [ ] `/api/generator/chat/sessions/*` 라우트 제거(있다면)

## ⑥ 테스트·검증

- [ ] slot_agent 업로드 키 전달 단위 테스트(LLM 스텁)
- [ ] 슬롯 SSE 노출 단위 테스트
- [ ] RAG retriever 랭킹·인용 단위 테스트
- [ ] `cd backend && uv run ruff format . && uv run ruff check . --fix`
- [ ] `cd backend && uv run pytest tests/ -v` (관련 범위)
- [ ] 프론트 — 채팅에서 상품 이미지 업로드 + "만들어줘" → 컴포즈 생성 → 결과 보기 동작 확인
- [ ] manage/advise 회귀 없음 확인

## 완료 기준

- `/chat` 한 화면에서 "광고 만들어줘" → (이미지 업로드 가능) → 슬롯 수집 패널 → 생성 → 완료 + 결과 보기.
- "관리/시뮬/자유질문"은 기존대로 의도분류로 분기(회귀 없음).
- generator 크리에이티브 질문 → KB 근거 답변 + 인용.
- `/generator-chat` 평행 트랙 제거, 코드 단일화.

## 범위 / 비범위

- 시뮬 서브에이전트 실제 구현은 시뮬 팀 몫(SIMULATE 자리만 인지).
- manage/시뮬 "화면 이동" 네비게이션 이벤트는 열린 항목(이번 범위 밖, 필요 시 별도).
- improve 모드 채팅 트리거는 이번 범위 밖(create만).

