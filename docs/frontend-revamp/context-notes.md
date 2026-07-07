<!-- 프론트 개편 루프 세션이 맥락 없이 이해하도록 정리한 배경·결정·구조 노트 -->

# 프론트 개편 — 컨텍스트 노트

> 이 문서는 **새 세션(맥락 없음)** 이 이 작업을 self-contained하게 이해하도록 정리한 것. 루프 시작 시 [checklist.md](checklist.md)와 함께 먼저 읽을 것.

## 무엇을 / 왜

ClickMe 프론트를 **사용자친화적 UI/UX로 전면 개편**한다. 색만이 아니라 정보구조(IA)·컴포넌트 체계·대시보드 재설계까지. 목표는 "기능만 도는 HTML" → **딱 봐도 사로잡히는 실서비스급.** 별도 브랜치라 **지금과 180° 달라져도 됨 — 자유롭게 재설계.**

## 절대 규칙 (어기면 안 됨)

1. **백엔드 append-only** — 기존 라우터/서비스/모델 수정·삭제 금지. 새 엔드포인트/테이블/Alembic 리비전만 추가 가능.
2. 프론트가 기존 API로 데이터를 못 얻으면 기존 걸 고치지 말고 **새 엔드포인트 추가** → `added-apis.md` 기록.
3. **기존 기능 동작을 0.1도 바꾸지 않는다.** 순수 UI/UX만.
4. Alembic 새 파일·`alembic upgrade head`·DB 조작 OK(추가 한정).
5. 테스트 데이터는 `test-data.md`에 기록 후 **작업 종료 시 삭제**.
6. 백엔드 `.py` 수정 시 커밋 전 Ruff(`uv run ruff format . && uv run ruff check . --fix`).
7. 한국어 출력, 새 파일 첫 줄 한국어 헤더 주석, 커밋 `타입: 한국어 설명`.

## 디자인 방향 (확정)

- **컨셉:** 토스 톤앤매너 재해석 — 미니멀·카드·여백·명확한 위계. 진입(`/`)은 Apple식 다이나믹.
- **색 전략:** 뉴트럴 우선(회색+여백+타이포가 화면 90%) + **색은 포인트에만**(주요 액션 1개·핵심 데이터 하이라이트·실제 semantic). 화면당 accent 1개. 의미 없는 색 금지.
- **기본 테마:** primary 파랑 `#3182F6`(기존 토스블루 유지) + 포인트 **바이올렛 `#7C3AED`**. (오렌지·노랑 비채택 — 노랑은 대비 약하고 warning과 충돌.)
- **테마 14종(= 포인트 색 프리셋):** 컬러11(blue⭐·indigo·cyan·emerald·orange·mono·wine·violet·rose·amber·teal) + 에디터다크3(monokai·monokai-black·dracula). `data-theme` 한 줄로 전환, `/themes` 갤러리에서 비교.
- **대시보드 원칙:** 5초 규칙 · 숫자보다 변화(델타) · "지금 할 일" 우선(이상감지/승인대기/리밸런스) · 멘탈모델 그룹 · 점진적 공개 · 허영지표 컷 · 역할별(USER/COMPANY/ADMIN) 분기 · 활동 피드.

## 코드 구조 (조사 결과)

- **스택:** Next.js 15.3 App Router(Turbopack) · React 19 · TS · Tailwind 3.4 · Recharts · XYFlow · pnpm 9.15. 현재 shadcn 미설치·framer-motion 미설치 → **이번 개편에서 shadcn 도입(P0.0) + framer-motion 도입(P1) 결정.** 아이콘은 lucide-react로 통일. 현재 브랜치 `feat/front-fix`.
- **토큰 위치:** `frontend/src/app/globals.css`(현재 CSS 변수 9개, `--color-*`) — **`tailwind.config.ts`에 색이 미배선**(폰트만 연결). 그래서 컴포넌트가 색을 하드코딩: 헥사 2747곳/136파일 + `bg-blue-500`류 233곳/57파일. **개편 토대 = 토큰을 tailwind에 배선 + 하드코딩 sweep.**
- **다크모드:** class 기반(`darkMode:'class'`), `ThemeProvider`(localStorage+OS), `html.dark`에서 CSS 변수 override. → 여기에 `data-theme` 레이어를 얹는다.
- **레이아웃:** `(app)` route group + `AppLayout`(사이드바+좌측패널 셸). 라우트 40+개, 역할 USER/COMPANY/ADMIN 분리.
- **공용 컴포넌트:** `components/ui/`에 KpiCard·Select·Pagination만(커스텀). 나머지 ~100개는 도메인별(chat 30+, manage, simulator). → **shadcn 도입 후 그 위에 우리 토큰을 배선**한 프리미티브(Button/Card/StatCard/Badge/Section 등)로 통일이 "정돈됨"의 핵심. 기존 커스텀 ui는 점진 대체(당장 삭제 금지, 동작 불변).

## 토큰 사용 규약 (P0 확정 — 화면 작업 시 준수)

shadcn CSS 변수를 **RGB 채널 트리플릿**으로 정의(`--primary: 49 130 246`), tailwind는 `rgb(var(--x) / <alpha-value>)`로 매핑 → `bg-primary/90` alpha 모디파이어 지원.

- **surface 위계:** `bg-surface-0`(페이지) `bg-surface-1`(hover/카드바닥) `bg-surface-2`(카드=`bg-card`) `bg-surface-3`(팝오버). 
- **텍스트 위계(ink):** `text-ink`(주) `text-ink-secondary` `text-ink-tertiary` `text-ink-muted` `text-ink-disabled`. shadcn 표준 `text-foreground`/`text-muted-foreground`도 동일 계열. (`text-primary`는 **파랑**이므로 본문 텍스트에 쓰지 말 것.)
- **보더(line):** `border-line`(기본=`border-border`) `border-line-strong` `border-line-stronger`.
- **primary(브랜드 파랑 #3182F6):** `bg-primary` `text-primary` `bg-primary-hover` `bg-primary-subtle`(연배경) `text-primary-foreground`.
- **point(브랜드 포인트 바이올렛 #7C3AED):** `bg-point` `text-point` `bg-point-hover` `bg-point-subtle` `text-point-foreground`. ⚠️ **shadcn `accent`(뉴트럴 hover)와 분리** — 브랜드 보라는 반드시 `point`, `accent`는 ghost/드롭다운 hover용 뉴트럴.
- **semantic 4종:** `success`/`warning`/`danger`/`info` 각각 `bg-{s}`(fg) `text-{s}` `bg-{s}-subtle`(배경) `border-{s}-border`. `destructive`=danger(shadcn 호환).
- **radius:** `rounded-lg`=12px(카드) `rounded-md` `rounded-sm` `rounded-xl`. **shadow:** `shadow-sm/md/lg`(다크 대응).
- **기존 `--color-*`**(color-primary/bg/surface/text-*/border/hover)는 새 토큰 alias로 유지 — 신규 코드는 위 토큰 사용, 기존 참조는 안 깨짐.
- ⚠️ **Windows 대소문자**: 파일명 `select.tsx`↔`Select.tsx` 충돌. 커스텀 `ui/Select.tsx` 유지, shadcn select 미설치.

## 검증 방식

화면 변경은 **`preview_*` 도구로 직접** 확인(수동 체크리스트 떠넘기기 금지). preview_start → 리로드 → console_logs/network로 에러 → snapshot으로 내용 → inspect(CSS)/click·fill(상호작용) → 스크린샷으로 증거. 문제(버그·콘솔에러·깨진링크) 발견 시 소스 고치고 재확인. 9시간 밤샘이니 **사소한 트러블도 그 자리에서 해결.**

## 실행 순서

**P0 토대(단독 선행)** → P1 셸·랜딩 → P2 대시보드 → P3 도메인화면 → P4 반응형 → P5 QA·마감. P0는 모든 화면이 의존하므로 반드시 먼저.

## 관련 파일

- 체크리스트: [checklist.md](checklist.md)
- 추가 API 로그: [added-apis.md](added-apis.md)
- 테스트 데이터 삭제 체크: [test-data.md](test-data.md)
- 프로젝트 규칙: 루트 `CLAUDE.md`, `frontend/`(pnpm)·`backend/`(uv) PM 교차 금지.
