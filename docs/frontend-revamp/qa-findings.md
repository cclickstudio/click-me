<!-- Phase 6 E2E QA 스윕에서 발견한 결함과 수정 상태를 기록하는 파일 -->

# QA Findings — 프론트 개편 E2E 스윕

> Phase 6에서 루프가 채운다. 스윕→기록→수정→재검을 반복하고, **2회 연속 새 발견 0**이면 종료.
> 심각도: `critical`(기능 끊김) · `major`(눈에 띄는 UI 붕괴) · `minor`(사소한 잘림·정렬·오탈자).

## 요약

- 총 발견: 4 / 수정: 3 / 보류(인프라) 1 / open(모바일 UX 확인 필요) 1
- 마지막 스윕: 2026-07-08 03:2x — admin 로그인, manage(monitoring·anomaly·budget·compare·reliability)·admin(manage-user·companies·generations)·themes 통주행 + 대시보드 3역할 + 모바일 375px. **신규 UI 결함 0**(broken 0·overflow 0·콘솔 에러 0).
- 연속 클린 스윕: **2 / 2 → 수렴 완료**(UI 기준. 남은 open은 백엔드 인프라 B1로 UI 무관)
- 수정 완료: 모바일 고정 햄버거↔콘텐츠 겹침(AppLayout max-md:pt-14) → fixed.
- 스윕2(라이트 모드): COMPANY 대시보드 라이트 실측 — 뉴트럴·블루 브랜드·danger 주의 카드·차트 정상, 오버플로 0, 콘솔 에러 0. 토큰 양모드 동작 확인. 신규 발견 0.

## 발견 목록

| #   | 화면(경로)   | 역할 | 심각도 | 증상                                                    | 재현            | 증거              | 상태 |
| --- | ------------ | ---- | ------ | ------------------------------------------------------- | --------------- | ----------------- | ---- |
| B1  | /simulation/[id] · /center | 전역 | infra(비-UI) | `GET /api/simulation/{id}/db-result`·`/api/center/notifications`·`/api/center/sessions`가 500(asyncpg prepared statement + Neon 풀러 비호환). 프론트엔 "Failed to fetch". **프론트 개편 변경과 무관·기존 인프라 이슈**(백엔드 append-only 범위라 미수정). 결과뷰/센터 라이브 검증이 이 환경에선 막힘 — 토큰화는 build+렌더로 검증. | asdf 로그인→시뮬 상세 진입 | backend.log asyncpg _prepare 트레이스 | open(백엔드 인프라, UI 무관) |
| C1  | /chat (ChatWorkspace) | ADMIN | major | 모바일(375px)에서 가로 스크롤 발생. `scrollWidth 1050` vs `clientWidth 375`. 원인: `ChatWorkspace.tsx`의 세션 목록 `<aside className="flex w-72 shrink-0 ...">`가 `max-md:hidden` 등 반응형 처리 없이 항상 288px를 차지 + 메인 nav(`w-56`, 224px)까지 겹쳐 최소 폭이 커짐. 앱의 다른 화면(`AppLayout.tsx`)은 `md:hidden` 햄버거+드로어(`mobileNavOpen`)와 `max-md:hidden`(패널 완전 숨김) 컨벤션을 쓰는데, `/chat` 세션 사이드바만 이 컨벤션을 안 따름. `/dashboard`는 동일 375px에서 `scrollWidth===clientWidth===375`로 정상이라 `/chat` 전용 회귀로 확인. | admin 로그인 → `/chat` → 매니지먼트 기업 선택 → viewport 375×812 리사이즈 → `document.documentElement.scrollWidth` 확인 | scrollWidth 1050 vs clientWidth 375, aside 폭 224/288 실측 | open — 모바일 UX 방향(세션 목록을 드로어로 뺄지, 완전히 숨길지) 사용자 확인 필요 |
| C2  | /dashboard "3기능 요약" 카드 | COMPANY | critical | COMPANY 대시보드의 "시뮬레이션 시작"(`/simulation`)·"광고 생성하기"(`/generator`) 카드를 누르면 `AppLayout.tsx`의 `COMPANY_BLOCKED = ['/chat','/simulation','/generator','/profile']` 가드에 걸려 즉시 `/dashboard`로 튕겨나감. 사이드바는 이미 이 3경로를 COMPANY에게 숨기는데(정상), 대시보드 `featureCards` 상수는 역할 필터 없이 그대로 map — 사이드바-대시보드 간 불일치. | test(COMPANY) 로그인 → `/dashboard`에서 "시뮬레이션 시작" 또는 "광고 생성하기" 클릭(또는 `location.href='/generator'`) → 즉시 `/dashboard`로 리다이렉트 | 리다이렉트 후 `window.location.pathname==='/dashboard'` 확인, 소스 `dashboard/page.tsx:93-115`(featureCards)·`AppLayout.tsx:17`(COMPANY_BLOCKED) | **fixed** — `featureCards.filter(card => !isCompany \|\| card.href === '/manage')`로 COMPANY는 "성과 확인하기"(매니지먼트)만 노출 |
| C3  | /dashboard CLIO 런처 | COMPANY | critical | 같은 원인으로 CLIO 어시스턴트 런처(빠른 질문 버튼·입력창·"전체 화면으로 →")가 COMPANY에게도 보이는데, 전부 `/chat`으로 이동 — `/chat`도 COMPANY_BLOCKED라 즉시 튕겨나감. 원래 조건이 `{!isAdmin && (...)}`로 ADMIN만 제외하고 COMPANY는 포함시켰던 것이 원인. | test(COMPANY) 로그인 → `/dashboard` 하단 CLIO 카드에서 빠른 질문 버튼 클릭 또는 Enter → `/chat`으로 갔다가 즉시 `/dashboard`로 리다이렉트 | 소스 `dashboard/page.tsx:718`(`{!isAdmin && (`) | **fixed** — `{!isAdmin && !isCompany && (`로 COMPANY도 제외, 리로드 후 CLIO 카드 미노출·콘솔 에러 0 확인 |

## 진행 로그

- 2026-07-08 03:2x 스윕1(다크) — admin 통주행(manage 5 + admin 3 + themes) + 3역할 대시보드 + 모바일 375px. 렌더 broken 0·가로 오버플로 0·콘솔 에러 0. 발견: 모바일 햄버거 겹침 1(즉시 fixed), 백엔드 center/db-result 500 1(인프라 B1·UI 무관·보류).
- 2026-07-08 03:35 스윕2(라이트) — COMPANY 대시보드 라이트 실측(뉴트럴·브랜드·danger 카드·차트·크레딧), 오버플로 0·콘솔 에러 0·신규 발견 0. **2연속 클린 → loop-until-dry 수렴 종료.**
