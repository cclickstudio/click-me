# 수동 점검 체크리스트 (Manual QA)

> 자동 테스트(pytest·Playwright)가 못 잡는, **사람이 화면으로 확인해야 하는** 항목들.
> Claude Preview(`preview_*` 도구)로 띄워 확인하거나 직접 브라우저로 점검한다.
>
> 기동 — 백엔드 `cd backend && uv run uvicorn api.main:app --reload --port 8000`
> / 프론트 `cd frontend && pnpm dev` (http://localhost:3000)

## 0. 기동·환경

- [ ] 백엔드 `http://localhost:8000/docs` 200, 라우터 정상 등록
- [ ] 프론트 `http://localhost:3000` 렌더, 콘솔 에러 없음
- [ ] `.env`(OPENAI_API_KEY 등) 로드 — 채팅·시뮬 실모드 동작

## 1. 광고 시뮬레이터 (4-1)

- [ ] 시뮬 폼(제목·카피·카테고리·목표) 입력 → 실행
- [ ] **4대 KPI** 표시 — 클릭 의향률(신뢰구간), 구매의도(1~5 평균+**분포 전체**), 신뢰도(1~5), 거부율(+사유 분해)
- [ ] "예측 CTR" 등 **실측 스케일 환산 표기 없음** (의향률은 구간·분포로만)
- [ ] 토론(debate) 스트림 위젯 표시 → 진행 → 요약
- [ ] 보고서/PDF 생성·다운로드 — **화면과 PDF 내용 일치**
- [ ] 새로고침 후 진행중/완료 시뮬 복원(세션 URL 재진입)

## 2. 광고 매니지먼트 (4-2)

- [ ] 캠페인 목록·성과·예산 단일 화면 조회
- [ ] 추천 조치 카드(RESULT/REVIEW) — 위험도(tier)·근거(rationale) 표시
- [ ] **승인 필요한 조치(HITL)** → 승인 화면 거쳐 실행(바로 실행 안 됨)
- [ ] 예산·상태 변경(일시중지·게재·증액/감액) 반영

## 3. 광고 생성 (4-3)

- [ ] 개선 시안 **3개 자동 생성 + 기대성과 순위** 표시
- [ ] 생성 폼(gen_form) → 결과(gen_result) 위젯 흐름
- [ ] 이미지·카피 렌더, 후보 카피로 시뮬 진입(제너→시뮬 루프)

## 4. 채팅 AI 어시스턴트 (4-4)

- [ ] SSE 스트리밍(토큰 점진 출력), 중단·에러 처리
- [ ] 의도 라우팅 — 시뮬/매니지/생성/일반 질문 각각 올바른 위젯·답변
- [ ] 위젯 렌더 — sim_form · sim_result · sim_list · gen_form · gen_result · approval · create_campaign · campaign_action
- [ ] **Deep Agent(복합 질의)**
  - [ ] "지난 시뮬 결과 해석해줘" → `ask_simulation`, 텍스트 답변(위젯 없음)
  - [ ] "이 광고 시뮬 돌려줘" → `run_simulation`, **sim_form 폼 표시**
  - [ ] "성과 보고 시안 만들어줘" → 매니지먼트+생성 엮은 답
  - [ ] 계획 체크리스트(plan, ⬜⏳✅)·추천조치 카드(meta.cards) 표시
- [ ] 웹 인용 칩(Tavily) 표시(해당 시)

## 5. 크로스 (전 화면 공통)

- [ ] 다크모드 토글 — 색·대비 정상(Toss 스타일)
- [ ] 반응형(모바일 폭) 레이아웃 깨짐 없음
- [ ] 로딩·빈 상태·에러 상태 UI 표시
- [ ] 기밀 데이터(예산·크리에이티브) **평문 로그 노출 없음**

## 메모 (로컬 점검 팁)

- 기동: 백엔드 8000 / 프론트 3000. PM은 backend=uv, frontend=pnpm.
- 로그인은 토큰 주입(`localStorage.clickme_token`) — `/sign-in` 폼 합성입력은 비신뢰.
- 채팅 위젯 영속은 DB(ChatSession/ChatMessage의 `meta.widget.type` 시퀀스)로 검증.
- 시뮬은 실 LLM 호출이라 1회 ~1분 — 타임아웃 넉넉히.
