# E2E·테스트 전담 세션 진행 체크리스트

> 이 세션은 테스트 파일만 수정한다(제너·채팅 소스·docs/chat/tasklist.md 금지).
> 브랜치 feat/e2e-tests에서만 작업·커밋. 매 반복 1단계.

## 단계

- ✅ **P1** 백엔드 pytest — `GET /api/admin/chats`가 `updated_at`(최근활동) 내림차순인지. (`tests/admin/test_chats_ordering.py`, 실 DB 통합, 초록)
- ⬜ **P2** Playwright 셋업 — `test/e2e/` + config + 토큰 로그인 헬퍼 + 건도연 진입 헬퍼, frontend `@playwright/test` devDep. (의존 없음)
- ⬜ **P3** E2E① 시뮬 영속 + 새로고침 복원 (가장 중요). [P2]
- ⬜ **P4** E2E② 위젯 타이밍 — 반응 완료 직후 결과 위젯 + 토론 위젯 둘 다 보임. [P2]
- ⬜ **P5** E2E③ N4 세션 누수 — A 시뮬이 B 세션 선제 알림으로 안 뜸. [P3]
- ⬜ **P6** CI(`.github/workflows/ci.yml`)에 테스트 스텝(E2E는 서버+브라우저+테스트DB 필요). [P3,P4,P5,P1]

## 메모

- 개인 DB ep-soft-band. backend=uv, frontend=pnpm.
- USER doyeon `73859b11-03bf-4b1c-80c3-7d7895ed5725`, ADMIN `2fb541e2-8abb-48ad-99f8-e2f1054d3d9d`, 프로젝트 건도연 `8b33546d-e763-44fb-a222-6f02ba9a6707`.
- 로그인은 토큰 주입(`localStorage.clickme_token`), /sign-in 폼 합성입력 비신뢰.
- 영속 검증은 DB(ChatSession/ChatMessage meta.widget.type 시퀀스)로.
