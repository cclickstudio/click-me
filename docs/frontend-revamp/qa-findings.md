<!-- Phase 6 E2E QA 스윕에서 발견한 결함과 수정 상태를 기록하는 파일 -->

# QA Findings — 프론트 개편 E2E 스윕

> Phase 6에서 루프가 채운다. 스윕→기록→수정→재검을 반복하고, **2회 연속 새 발견 0**이면 종료.
> 심각도: `critical`(기능 끊김) · `major`(눈에 띄는 UI 붕괴) · `minor`(사소한 잘림·정렬·오탈자).

## 요약

- 총 발견: 5 / 수정: 5 / 보류(인프라) 1
- 마지막 스윕: 2026-07-08 03:2x — admin 로그인, manage(monitoring·anomaly·budget·compare·reliability)·admin(manage-user·companies·generations)·themes 통주행 + 대시보드 3역할 + 모바일 375px. **신규 UI 결함 0**(broken 0·overflow 0·콘솔 에러 0).
- 연속 클린 스윕: **2 / 2 → 수렴 완료**(UI 기준. 남은 open은 백엔드 인프라 B1로 UI 무관)
- 수정 완료: 모바일 고정 햄버거↔콘텐츠 겹침(AppLayout max-md:pt-14) → fixed.
- 스윕2(라이트 모드): COMPANY 대시보드 라이트 실측 — 뉴트럴·블루 브랜드·danger 주의 카드·차트 정상, 오버플로 0, 콘솔 에러 0. 토큰 양모드 동작 확인. 신규 발견 0.

## 발견 목록

| #   | 화면(경로)   | 역할 | 심각도 | 증상                                                    | 재현            | 증거              | 상태 |
| --- | ------------ | ---- | ------ | ------------------------------------------------------- | --------------- | ----------------- | ---- |
| B1  | /simulation/[id] · /center | 전역 | infra(비-UI) | `GET /api/simulation/{id}/db-result`·`/api/center/notifications`·`/api/center/sessions`가 500(asyncpg prepared statement + Neon 풀러 비호환). 프론트엔 "Failed to fetch". **프론트 개편 변경과 무관·기존 인프라 이슈**(백엔드 append-only 범위라 미수정). 결과뷰/센터 라이브 검증이 이 환경에선 막힘 — 토큰화는 build+렌더로 검증. | asdf 로그인→시뮬 상세 진입 | backend.log asyncpg _prepare 트레이스 | open(백엔드 인프라, UI 무관) |
| C1  | /chat (ChatWorkspace) | ADMIN | major | 모바일(375px)에서 가로 스크롤 발생. `scrollWidth 1050` vs `clientWidth 375`. 원인: `ChatWorkspace.tsx`의 세션 목록 `<aside className="flex w-72 shrink-0 ...">`가 `max-md:hidden` 등 반응형 처리 없이 항상 288px를 차지 + 메인 nav(`w-56`, 224px)까지 겹쳐 최소 폭이 커짐. 앱의 다른 화면(`AppLayout.tsx`)은 `md:hidden` 햄버거+드로어(`mobileNavOpen`)와 `max-md:hidden`(패널 완전 숨김) 컨벤션을 쓰는데, `/chat` 세션 사이드바만 이 컨벤션을 안 따름. `/dashboard`는 동일 375px에서 `scrollWidth===clientWidth===375`로 정상이라 `/chat` 전용 회귀로 확인. | admin 로그인 → `/chat` → 매니지먼트 기업 선택 → viewport 375×812 리사이즈 → `document.documentElement.scrollWidth` 확인 | scrollWidth 1050 vs clientWidth 375, aside 폭 224/288 실측 | **fixed** — 사용자 확인 후 `Sidebar.tsx`와 동일한 햄버거+드로어 패턴 적용(`mobileSidebarOpen` state, `max-md:fixed`+`translate-x` 슬라이드+백드롭). 리로드 후 `scrollWidth===clientWidth===375` 재확인 |
| C2  | /dashboard "3기능 요약" 카드 | COMPANY | critical | COMPANY 대시보드의 "시뮬레이션 시작"(`/simulation`)·"광고 생성하기"(`/generator`) 카드를 누르면 `AppLayout.tsx`의 `COMPANY_BLOCKED = ['/chat','/simulation','/generator','/profile']` 가드에 걸려 즉시 `/dashboard`로 튕겨나감. 사이드바는 이미 이 3경로를 COMPANY에게 숨기는데(정상), 대시보드 `featureCards` 상수는 역할 필터 없이 그대로 map — 사이드바-대시보드 간 불일치. | test(COMPANY) 로그인 → `/dashboard`에서 "시뮬레이션 시작" 또는 "광고 생성하기" 클릭(또는 `location.href='/generator'`) → 즉시 `/dashboard`로 리다이렉트 | 리다이렉트 후 `window.location.pathname==='/dashboard'` 확인, 소스 `dashboard/page.tsx:93-115`(featureCards)·`AppLayout.tsx:17`(COMPANY_BLOCKED) | **fixed** — `featureCards.filter(card => !isCompany \|\| card.href === '/manage')`로 COMPANY는 "성과 확인하기"(매니지먼트)만 노출 |
| C3  | /dashboard CLIO 런처 | COMPANY | critical | 같은 원인으로 CLIO 어시스턴트 런처(빠른 질문 버튼·입력창·"전체 화면으로 →")가 COMPANY에게도 보이는데, 전부 `/chat`으로 이동 — `/chat`도 COMPANY_BLOCKED라 즉시 튕겨나감. 원래 조건이 `{!isAdmin && (...)}`로 ADMIN만 제외하고 COMPANY는 포함시켰던 것이 원인. | test(COMPANY) 로그인 → `/dashboard` 하단 CLIO 카드에서 빠른 질문 버튼 클릭 또는 Enter → `/chat`으로 갔다가 즉시 `/dashboard`로 리다이렉트 | 소스 `dashboard/page.tsx:718`(`{!isAdmin && (`) | **fixed** — `{!isAdmin && !isCompany && (`로 COMPANY도 제외, 리로드 후 CLIO 카드 미노출·콘솔 에러 0 확인 |
| C4  | 전역 다크모드 카드 테두리 | 전역 | major | 다크모드에서 `Card`(`components/ui/card.tsx`) 테두리가 밝은 회색으로 떠 눈에 거슬림(사용자 리포트: "테두리 하얀색"). 원인: `Card`가 bare `border` 클래스를 쓰는데, Tailwind 코어 프리셋이 `borderColor.DEFAULT`를 gray-200(#E5E7EB)으로 고정 — `tailwind.config.ts`에 `colors.border`를 `--border`로 확장해도 `borderColor.DEFAULT`는 별도 설정이라 안 따라옴. 라이트모드는 우연히 거의 같은 색이라 안 보였을 뿐. | 임의 페이지(예: `/dashboard`) 다크모드 진입 → StatCard 등 `Card` 테두리 확인, `getComputedStyle` 상 `border-top-color`가 `--border` 토큰이 아닌 고정값 | admin 로그인 → 다크모드 → `preview_inspect`로 `border-top-color: rgb(229,231,235)`(고정 gray-200) vs `--border` 값(당시 30,41,59) 불일치 확인 | **fixed** — `tailwind.config.ts`에 `borderColor: { DEFAULT: withOpacity('--border') }` 추가(전역 1곳 수정으로 bare `border` 클래스 전체 반영). 다크 `--border`/`--border-strong`/`--border-stronger`도 카드 배경보다 어두운 그림자 톤(`rgb(6,10,19)` 등)으로 낮춤(사용자 피드백 반영) |

## 진행 로그

- 2026-07-08 03:2x 스윕1(다크) — admin 통주행(manage 5 + admin 3 + themes) + 3역할 대시보드 + 모바일 375px. 렌더 broken 0·가로 오버플로 0·콘솔 에러 0. 발견: 모바일 햄버거 겹침 1(즉시 fixed), 백엔드 center/db-result 500 1(인프라 B1·UI 무관·보류).
- 2026-07-08 03:35 스윕2(라이트) — COMPANY 대시보드 라이트 실측(뉴트럴·브랜드·danger 카드·차트·크레딧), 오버플로 0·콘솔 에러 0·신규 발견 0. **2연속 클린 → loop-until-dry 수렴 종료.**
- 2026-07-09 스윕3(오늘 낮 세션 이후 회귀) — ADMIN/COMPANY/USER 3역할 전수: 로그인·대시보드·`/admin/inquiry`(신규 DB 기능)·`/admin/dashboard`·`/admin/chat-log`·`/admin/check`(모두 404 삭제 확인)·`/manage/reliability`(사이드바 노출 확인)·`/chat` 워크스페이스(새 채팅→메시지 전송→CLIO 응답, 순서 정상)·`/generator` 칩 UI·company/*(projects·teams·members·credits)·다크/라이트 토글·랜딩(useScroll 에러 재발 없음)·모바일 375px 통주행. 신규 발견 3(C1~C3), 즉시 수정 2(C2·C3, COMPANY 대시보드가 자기 역할에서 차단된 라우트로 안내하던 치명적 불일치), 사용자 확인 대기 1(C1, `/chat` 모바일 반응형). 이번 스윕은 개발 서버 환경(Windows Turbopack, `.next` 매니페스트 파일에 대한 반복적 EPERM 잠금 — 백신 실시간 검사로 추정)이 매우 불안정해 라우트 컴파일이 간헐적으로 30~200초·때때로 일시적 500을 유발했음 — 전부 재시도 시 정상 복구되어 앱 버그가 아닌 환경 이슈로 확인, `frontend/.next`를 백신 예외 경로로 추가하면 해결될 가능성 높음.
- 2026-07-09 후속 — C1 사용자 확인(햄버거+드로어 방식 승인) 후 `ChatWorkspace.tsx`에 적용, 리로드로 오버플로 해소 재확인. 별도로 사용자가 다크모드 카드 테두리 이슈("테두리 하얀색")를 리포트 — 원인 추적 결과 C4(전역 Tailwind `borderColor.DEFAULT` 미설정) 발견·수정. 컬러 테마 14종(색상 11 + 에디터다크 3)을 사용자 요청으로 전량 제거하고 블루 단일 테마로 정리(`themes.css`·`/themes` 갤러리 페이지 삭제, `ThemeProvider`·`chart-theme.ts`·`layout.tsx` 단순화) — 별도 QA 발견은 아니고 기능 축소 요청.
