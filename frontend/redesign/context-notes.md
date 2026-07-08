# 프론트엔드 UI/UX 전면 개편 — Context Notes

> 이 문서는 개편의 배경·목표·현황 진단·제약·미결정 갈림길을 담은 단일 기준(single source)이다.
> 실제 코드 개편은 진행 중인 검증/구현 워크트리(sim-debate-verify · sim-pdf-verify · chat-loop-earlystop)가
> 병합되어 프론트 baseline이 하나로 굳은 뒤 착수한다. 이 문서와 [design-system.md](./design-system.md),
> [checklist.md](./checklist.md)는 그때까지 미리 완성해 두는 선행 산출물이다.

## 1. 왜 하는가 (목표)

- **"싹 갈아엎기"** — 현재 화면을 부분 수선하는 게 아니라, 디자인 시스템(토큰·컴포넌트·레이아웃 규칙)을
  먼저 세우고 그 위에서 전 페이지를 일관되게 다시 짠다.
- **모바일 전 기능 사용 가능** — 폰으로 접속해도 모든 핵심 기능(시뮬·매니지먼트·생성·채팅)을 순조롭게 쓸 수 있게.
  현재 대부분 페이지가 데스크톱 고정폭이라 모바일에서 깨진다. 개편과 반응형을 **한 번에** 처리한다.
- **일관성·유지보수성** — 색/간격/타이포/컴포넌트가 페이지마다 제각각인 상태를 시맨틱 토큰 기반으로 통일.

## 2. 현황 진단 (조사 결과 요약)

### 2.1 디자인 토대
- **색상**: `frontend/src/app/globals.css`에 CSS 변수로 라이트/다크 팔레트 정의됨(Toss 블루 `#3182F6` 계열).
  `--color-primary/-hover`, `--color-bg/-surface/-hover/-border`, `--color-text-primary/-secondary/-tertiary`.
- **문제**: `frontend/tailwind.config.ts`의 `theme.extend`에 **`colors`가 없다** — fontFamily만 연결.
  → 개발자가 `bg-[var(--color-surface)]` 임의값이나 하드코딩 hex를 쓰게 되어 일관성이 무너짐.
  → **1순위 개선: CSS 변수를 Tailwind 시맨틱 토큰(`bg-surface`, `text-secondary`, `border-default` 등)으로 승격.**
- **브레이크포인트**: 커스텀 없음(Tailwind 기본 sm 640 / md 768 / lg 1024 / xl 1280).
- **테마**: `ThemeProvider.tsx` light/dark 토글 + localStorage + prefers-color-scheme 초기화 — 양호. 유지.
- **접근성**: `:focus-visible` 링, `prefers-reduced-motion` 대응, 키보드 포커스 분리 — 이미 존재. 개편 시 보존·확장.

### 2.2 반응형 현황 (모바일 깨짐 지점)
- **공통 셸** `AppLayout.tsx` — 햄버거 메뉴·사이드바 드로어(`max-md:-translate-x-full`)·좌측 패널 숨김(`max-md:hidden`)은
  이미 있음. 사이드바 내부 콘텐츠는 모바일 최적화 안 됨(`w-56` 고정).
- **대시보드** `dashboard/page.tsx` — `grid-cols-3`·`grid-cols-2` 고정 → 모바일 오버플로우. 테이블 하드코딩 폭. 챗봇 `h-64` 고정.
- **캠페인** `manage/campaigns/page.tsx` + `CampaignTable.tsx` — 8~13컬럼 고정 테이블. 모바일에서 카드뷰 전환 필요.
- **성과 비교** `manage/compare/page.tsx` — `grid-cols-4` 고정 → 모바일 심하게 깨짐.
- **매니지먼트 홈** `manage/page.tsx` — `grid-cols-1 md:grid-cols-4`로 **유일하게 올바른 반응형**. 이걸 표준 패턴으로 삼는다.
- **유틸 부재**: `useMediaQuery`/`useIsMobile`/`useWindowSize` 훅 없음. 범용 Drawer/Modal 컴포넌트 없음(AppLayout 내부 구현만).

### 2.3 전체 라우트
페이지별 개편 대상·우선순위는 [checklist.md](./checklist.md) 참고. (인증/정적, `(app)` 사용자 기능, `admin/*`, `company/*` 그룹)

## 3. 제약 (건드리지 않는 것 / 지켜야 할 것)

- **백엔드 API 계약 불변** — 개편은 프론트 표현 계층만. 응답 스키마·엔드포인트는 그대로 소비.
- **PM 규칙** — `frontend/`는 pnpm 전용(uv 금지). 라이브러리 추가는 `pnpm add`.
- **다크모드 유지** — 라이트/다크 둘 다 1급 지원. 새 토큰도 두 테마 모두 정의.
- **접근성 회귀 금지** — 현재 focus-visible/reduced-motion 대응을 최소한 유지, 가능하면 강화(대비·터치 타깃 44px).
- **한국어 UI** — 카피·라벨 한국어. 문장 끝 콜론 금지 규칙은 코드 아닌 문구에 적용.
- **문서 자동생성** — 라우트 추가/삭제/경로 변경 시 `backend/scripts/gen_docs.py`로 `docs/frontend-routes.md` 재생성.

## 4. 미결정 갈림길 (착수 전 도연님 확정 필요)

아래 4.1·4.2는 **확정**(2026-07-07). 4.3·4.4는 병합 후 착수 시점 확정.

### 4.1 컴포넌트 라이브러리 — ✅ 확정: **shadcn/ui 도입**
- **이유**: Radix 기반 접근성(키보드·ARIA·포커스 트랩)·다크모드·반응형이 기본 내장. 코드 소유(복붙 방식)라 Tailwind 토큰에 그대로 녹임.
  Drawer/Dialog/Sheet(모바일 바텀시트)/Select/Table 등 지금 없는 것들을 빠르게 확보 → 반응형 개편 가속.
- **셋업 시 할 일**: `pnpm dlx shadcn@latest init` → 색/라운드를 §design-system 토큰에 맞춰 설정 →
  Button/Card/Dialog/Sheet/Select/Tabs/Table/Toast 우선 도입 → 기존 `ui/Select.tsx` 등과 중복 정리.
- **비용/리스크**: 초기 셋업 ≈1일. 번들 영향은 tree-shaking으로 제한적.

### 4.2 디자인 톤/레퍼런스 — ✅ 확정: **현 Toss 계열 유지·정제**
- 현재 팔레트가 이미 Toss 블루 기반의 깔끔한 SaaS 톤. 이를 **정제·확장**(간격·라운드·그림자 체계화, 데이터 시각화 색 추가)한다.
  전면 리브랜딩 안 함. 로고/브랜드 컬러는 현행 유지.

### 4.3 데이터 시각화 — 권장: **차트 라이브러리 1종 표준화**
- 시뮬 KPI 분포·매니지먼트 성과 그래프가 많음. 현재 라이브러리/구현이 혼재하는지 병합 후 확인 필요.
- 권장: Recharts 또는 이미 쓰는 것 하나로 통일 + 반응형 컨테이너 래퍼 1개. (확정은 병합 후 실제 코드 확인하고.)

### 4.4 개편 범위/순서 — 권장: **레이아웃 셸 → 디자인 토큰 → 페이지 그룹별**
- 자세한 페이지 우선순위·워크트리 분할안은 [checklist.md](./checklist.md).

## 5. 진행 순서 (전체 그림)

1. **(지금·선행)** 이 문서 3종 완성 — context-notes / design-system / checklist. **코드 변경 없음**.
2. **(도연님)** §4 갈림길 확정(특히 shadcn 도입 여부).
3. **(병합 대기)** sim-debate-verify · sim-pdf-verify · chat-loop-earlystop 병합 → 프론트 baseline 확정.
4. **(착수)** baseline 위에서 워크트리 재분할(셸/토큰 먼저 → 페이지 그룹별 병렬) 후 개편 구현.
5. 각 페이지 개편마다 Claude Preview로 모바일/데스크톱·라이트/다크 검증(스크린샷 증거).

## 6. 관련 파일 (개편 착수 시 진입점)

- 토큰 원본: `frontend/src/app/globals.css`
- Tailwind 설정: `frontend/tailwind.config.ts` ← 시맨틱 토큰 매핑 추가
- 테마: `frontend/src/components/ThemeProvider.tsx`
- 셸: `frontend/src/components/AppLayout.tsx` · `Sidebar.tsx` · `Center.tsx` · `ProjectPanel/CompanyPanel/AdminPanel.tsx`
- 공용 UI: `frontend/src/components/ui/*`
