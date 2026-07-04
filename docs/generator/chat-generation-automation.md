# 생성 기능 채팅 자동화 계획 (2026-07-04)

> 채팅(4-4)에서 생성(4-3)을 사람 개입 최소로 완주시키기 위한 계획.
> 인터뷰 확정 사항 — Q1: 필수값 완비 시 폼 스킵 즉시 실행(b) / Q2: 진행 카드 SSE(a) /
> Q3: 시뮬 KPI 루프는 옵션형(b) / Q4: KB 환류는 **취소**(범위 제외).

## Phase 1+2 — 폼 스킵 즉시 실행 + 진행 카드 ✅ (2026-07-04 구현)

- [x] `run_generation` 도구 — 상품명·설명·타깃·프로젝트 완비 시 `start_generation()` 직접 호출,
      부족하면 기존 `gen_form` 폴백 (`api/assistant/subagent_tools.py`)
- [x] `run_improvement` 도구 — 시뮬 프리필(simulation_summary·product_name) + 프로젝트 완비 시
      IMPROVE 즉시 시작, 아니면 개선 폼 폴백
- [x] `created_by` 전파 — 채팅 state의 user_id → `start_generation(created_by=...)`
      (`domain/generator/assistant/tools.py` `_parse_uuid`·`start_improve_generation`)
- [x] `widgets.gen_progress(generation_id, stream_url)` 추가 (`domain/chat/widgets.py`)
- [x] 프론트 `GenProgressWidget` — `/generations/{id}/stream` SSE 구독, 진행률 → 완료 시
      `handleGenComplete`로 `gen_result` 위젯 발화. 새로고침 복원 시 인라인 요약만(중복 방지)
- [x] `prompts.py` — 지어낸 값 즉시 실행 방지 경고("발화에 없는 값은 비워라") 추가
- [x] 테스트 — 완비/미완비/프로젝트 없음 분기 (`test_tools.py`·`test_improve_tool.py`)

**상품 이미지 처리 (2026-07-04 보강)** — 즉시 실행이 이미지를 조용히 건너뛰지 않도록 3분기.
- 이번 턴 이미지 첨부(`ChatRequest.image_url` → state `has_image`) → **폼 경로**
  (첨부가 상품 이미지로 프리필, 실행 클릭만)
- 이미지 의사 미확인 → 시작 전 **되묻기**(첨부해서 답하거나 '이미지 없이 진행')
- '이미지 없이/무형 상품' 확인(`skip_product_image=True`) → 즉시 실행
- `gen_loop`(자동 개선 루프) 카드는 프론트 렌더러가 여전히 없다(기존 공백). `GenProgressWidget`
  패턴으로 후속 추가 가능.

## Phase 3 — 옵션형 시뮬 KPI 루프 (미착수)

- [ ] `generation_loop.start_loop`에 `eval_mode: "qa" | "simulation"` 추가 (기본 qa, 무변경)
- [ ] **시뮬 팀(도연·태호)과 contracts 진입점 합의** — 후보(이미지+카피) → 4대 KPI 반환 인터페이스.
      타 도메인 내부 직접 import 금지(협업 규칙)
- [ ] 최저 KPI 축 → `kb/ad_image_guide.md` "개선 패턴 —" 4청크 매핑 → `GenKbRetriever` 검색으로
      개선 지시문 생성
- [ ] KPI는 반복 간 비교용 내부 신호로만(실측 환산 금지 원칙) — 사용자 표시는 분포·CI 유지
- [ ] 가드 — 시뮬 모드 `max_iterations` 기본 2, 프로젝트당 동시 루프 1개
- [ ] `improve_ad_iteratively`에 `use_simulation` 파라미터 + 프롬프트 정책
      ("시뮬 기준으로 반복 개선" 명시 발화 시에만)

## 관련 구현 (선행 완료)

- 생성 후반 워크플로우 채팅 도구 7종(확정·게시·리레이아웃·ZIP·브랜드키트) — 2026-07-04.
  게시(`publish_ad_candidate`)는 confirm 2단계 게이트 유지.
