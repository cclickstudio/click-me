# 디자인 시스템 초안 — 토큰 · Tailwind 설정 · 컴포넌트 규칙

> 개편의 기반이 되는 디자인 토큰과 Tailwind 매핑, 반응형·컴포넌트 표준을 정의한다.
> 현재 `globals.css`의 CSS 변수를 확장하고, `tailwind.config.ts`에 시맨틱 토큰으로 연결하는 것이 1순위 작업.

## 1. 색상 토큰 (Semantic Color Tokens)

### 1.1 원칙
- 컴포넌트는 **hex를 직접 쓰지 않는다**. 항상 시맨틱 토큰(`bg-surface`, `text-secondary`, `border-default`)을 쓴다.
- 값은 `globals.css`의 CSS 변수 한 곳에서만 정의 → 라이트/다크가 자동 전환.
- opacity modifier(`bg-primary/10`)를 쓰려면 변수를 **채널 방식**으로 두어야 한다(아래 1.3).

### 1.2 현재 팔레트 (globals.css — 유지 + 확장)
| 토큰 | 라이트 | 다크 | 용도 |
|---|---|---|---|
| primary | `#3182F6` | 동일 | 주요 액션·링크·강조 |
| primary-hover | `#1B6EEB` | 동일 | hover |
| bg | `#F9FAFB` | `#0F1117` | 페이지 배경 |
| surface | `#FFFFFF` | `#1C2333` | 카드·패널 |
| hover | `#F2F4F6` | `#252D3D` | hover 배경 |
| border | `#E5E8EB` | `#2D3748` | 구분선·테두리 |
| text-primary | `#191F28` | `#F2F4F6` | 본문 |
| text-secondary | `#8B95A1` | `#6B7280` | 보조 |
| text-tertiary | `#B0B8C1` | `#4B5563` | 비활성·플레이스홀더 |

### 1.3 확장 제안 (개편 시 추가)
현재 팔레트에 없어서 페이지마다 하드코딩되기 쉬운 것들 — **시맨틱 상태색 + 데이터 시각화색**을 추가한다.

```css
/* globals.css :root 에 추가 (다크는 html.dark 에 대응값) */
:root {
  /* 상태 (성공/경고/위험/정보) — 라이트 */
  --color-success: #12B886;
  --color-warning: #F59F00;
  --color-danger:  #FA5252;
  --color-info:    #3182F6;
  /* surface 계층 (겹치는 카드/모달용) */
  --color-surface-2: #F2F4F6;   /* 다크: #252D3D */
  /* 데이터 시각화 팔레트 (차트 시리즈, 색맹 배려 순서) */
  --chart-1: #3182F6; --chart-2: #12B886; --chart-3: #F59F00;
  --chart-4: #7048E8; --chart-5: #FA5252; --chart-6: #15AABF;
}
```
> ⚠️ opacity modifier가 필요하면(`bg-success/10` 등) 위 hex를 `R G B`(공백 구분) 채널값으로 바꾸고
> Tailwind 매핑을 `rgb(var(--color-success) / <alpha-value>)`로 한다. 채널 전환은 개편 초기에 일괄 결정.

### 1.4 Tailwind 매핑 (tailwind.config.ts — 핵심 변경)
```ts
// theme.extend.colors 에 추가 (hex 변수 그대로 매핑하는 단순안)
colors: {
  primary: {
    DEFAULT: 'var(--color-primary)',
    hover: 'var(--color-primary-hover)',
  },
  bg: 'var(--color-bg)',
  surface: {
    DEFAULT: 'var(--color-surface)',
    2: 'var(--color-surface-2)',
  },
  hover: 'var(--color-hover)',
  border: { DEFAULT: 'var(--color-border)' },
  text: {
    primary: 'var(--color-text-primary)',
    secondary: 'var(--color-text-secondary)',
    tertiary: 'var(--color-text-tertiary)',
  },
  success: 'var(--color-success)',
  warning: 'var(--color-warning)',
  danger: 'var(--color-danger)',
  info: 'var(--color-info)',
},
```
→ 이후 `bg-surface`, `text-text-secondary`(또는 별칭 정리), `border-border`, `text-primary` 등으로 사용.
> 네이밍 충돌 정리: `text-primary`가 "글자색 primary"인지 "텍스트=본문"인지 헷갈리므로,
> **글자색은 `text-fg`/`text-fg-muted`, 브랜드색은 `primary`** 로 별칭을 재정리하는 안을 개편 초기에 확정.

## 2. 타이포그래피

- 폰트: 유지 — `var(--font-sans)`(NotoSansKR / Pretendard).
- 스케일(Tailwind 기본 + 용도 지정):
  | 용도 | 클래스 | 크기 |
  |---|---|---|
  | 페이지 타이틀 | `text-2xl font-bold` | 24px |
  | 섹션 헤딩 | `text-lg font-semibold` | 18px |
  | 본문 | `text-sm` / `text-base` | 14~16px |
  | 보조/캡션 | `text-xs text-text-secondary` | 12px |
- 모바일에서 타이틀 축소: `text-xl sm:text-2xl` 식으로 단계화.

## 3. 간격 · 라운드 · 그림자

- **radius**: 카드/버튼 `rounded-xl`(12px), 작은 요소 `rounded-lg`(8px), pill `rounded-full`. 통일.
- **shadow**: 카드 기본 `shadow-sm`, 떠 있는 요소(드롭다운/모달) `shadow-lg`. 다크모드에선 그림자 대신 `border`로 층 구분.
- **간격 리듬**: 섹션 `space-y-6`, 카드 내부 `p-4 sm:p-5`, 페이지 컨테이너 `px-4 sm:px-6 lg:px-8`.

## 4. 반응형 표준 (Mobile-First)

### 4.1 브레이크포인트 (Tailwind 기본 유지 — 커스텀 최소화)
- `sm` 640 · `md` 768 · `lg` 1024 · `xl` 1280. 필요 시 `xs`(예: 480) 추가는 개편 중 판단.

### 4.2 표준 그리드 패턴 (고정 `grid-cols-N` 금지)
```
grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3   // 카드 3열 → 태블릿 2 → 모바일 1
grid grid-cols-1 md:grid-cols-4                    // 매니지먼트 홈(현행 올바른 패턴)
```
- **표준 컨테이너**: `mx-auto w-full max-w-screen-xl px-4 sm:px-6 lg:px-8`.

### 4.3 테이블 → 모바일 대응
- 컬럼 많은 테이블(캠페인 8~13열)은 **`md` 미만에서 카드 리스트로 전환**하거나 핵심 2~3열만 노출.
- 최후수단은 `overflow-x-auto` 래퍼(가로 스크롤)지만, 핵심 데이터는 카드뷰 우선.

### 4.4 useMediaQuery 훅 신설
```ts
// frontend/src/hooks/useMediaQuery.ts — 신규
// SSR 안전(초기 false), matchMedia 구독. useIsMobile = useMediaQuery('(max-width: 767px)')
```
- 레이아웃 분기(테이블↔카드, 드로어 자동 닫힘)에 사용. CSS로 해결 가능한 건 CSS 우선, JS 분기가 꼭 필요할 때만.

### 4.5 터치 타깃
- 버튼/링크 최소 히트영역 44×44px. 아이콘 버튼도 `p-2.5` 이상.

## 5. 컴포넌트 규칙

### 5.1 라이브러리 방향
- **권장: shadcn/ui 도입**(context-notes §4.1). 도입 시 Drawer/Sheet(모바일 바텀시트)·Dialog·DropdownMenu·Select·Tabs·
  Table·Toast를 표준으로. 전부 Tailwind 토큰(위 §1.4)에 맞춰 색을 조정.
- 미도입 시: `ui/*` 자체 컴포넌트를 토큰 기반으로 리팩터 + Drawer/Dialog 직접 구현.

### 5.2 공통 컴포넌트 목록 (개편 후 갖춰야 할 것)
- `Button`(variant: primary/secondary/ghost/danger, size sm/md), `Card`, `Input`, `Select`(기존 확장),
  `Drawer`/`Sheet`(모바일), `Dialog/Modal`, `Tabs`, `Table`(반응형), `Badge`, `Toast`, `Skeleton`(로딩),
  `EmptyState`, `Pagination`(기존), `KpiCard`(기존 토큰화), 차트 반응형 래퍼.

### 5.3 셸(Shell)
- `AppLayout` — 데스크톱 3영역(사이드바+콘텐츠+우측 센터) 유지. 모바일은 사이드바 드로어 + 우측 센터도 드로어/시트화.
- 사이드바 내부를 모바일에서 스크롤·터치 친화적으로(현재 `w-56` 고정 내용).

## 6. 다크모드 · 접근성 체크

- 모든 새 토큰은 `:root`와 `html.dark` 양쪽 정의. 하드코딩 hex 금지로 자동 전환 보장.
- `:focus-visible` 링·`prefers-reduced-motion` 대응 유지(globals.css 기존). 대비 WCAG AA 목표.
- 이미지 alt, 폼 label 연결, 키보드 내비게이션(드로어 포커스 트랩) 확인.

## 7. 착수 초기 3개 커밋 단위 (병합 후)

1. `add: 디자인 토큰 확장(globals.css 상태색·차트색) + tailwind.config 시맨틱 매핑`
2. `add: useMediaQuery 훅 + 반응형 표준 컨테이너/그리드 유틸`
3. `edit: 공통 셸(AppLayout·Sidebar) 모바일 정제` → 이후 페이지 그룹별 병렬
