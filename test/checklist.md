# E2E·테스트 전담 세션 진행 체크리스트

> 이 세션은 테스트 파일만 수정한다(제너·채팅 소스·docs/chat/tasklist.md 금지).
> 브랜치 feat/e2e-tests에서만 작업·커밋. 매 반복 1단계.

## 단계

- ✅ **P1** 백엔드 pytest — `GET /api/admin/chats`가 `updated_at`(최근활동) 내림차순인지. (`tests/admin/test_chats_ordering.py`, 실 DB 통합, 초록)
- ✅ **P2** Playwright 셋업 — `playwright.config.ts` + `test/e2e/`(global-setup 토큰발급·auth/project 헬퍼·smoke), frontend `@playwright/test` devDep. smoke 초록. (의존 없음)
- ✅ **P3** E2E① 시뮬 영속 + 새로고침 복원 — `sim-persist.spec.ts`(실 시뮬 1회, 표본 1명). DB(`db_query.py`)로 sim_input·sim_result·debate_stream + ad_title 확인, 세션 URL 재진입 복원. 초록. [P2]
- ✅ **P4** E2E② 위젯 타이밍 — `widget-timing.spec.ts`. 결과 위젯("✅ 시뮬레이션 결과"+KPI) 직후 토론 위젯("AI 소비자 토론을 시작했어요") 둘 다 보임. 초록. [P2]
- ✅ **P5** E2E③ N4 세션 누수 — `session-leak.spec.ts`. A 완료→seen 등록 확인, B(가드 해제 폴링) 선제 알림 부재, 대조(seen에서 빼면 뜸)까지. 초록. [P3]
- ✅ **P6** CI — `ci.yml`에 `workflow_dispatch` + E2E 잡(수동 전용: DB·브라우저·서버 기동 후 `pnpm test:e2e`). P1은 기존 backend 잡에서 실행(실 DB 없으면 skip, 있으면 실행) + E2E 잡에서 실 DB로 재실행. YAML 검증·ruff 통과. [P3,P4,P5,P1]

## 메모

- 개인 DB ep-soft-band. backend=uv, frontend=pnpm.
- USER doyeon `73859b11-03bf-4b1c-80c3-7d7895ed5725`, ADMIN `2fb541e2-8abb-48ad-99f8-e2f1054d3d9d`, 프로젝트 건도연 `8b33546d-e763-44fb-a222-6f02ba9a6707`.
- 로그인은 토큰 주입(`localStorage.clickme_token`), /sign-in 폼 합성입력 비신뢰.
- 영속 검증은 DB(ChatSession/ChatMessage meta.widget.type 시퀀스)로.
