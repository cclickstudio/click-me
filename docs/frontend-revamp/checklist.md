<!-- 프론트 UI/UX 전면 개편 밤샘 루프용 마스터 체크리스트 -->

# ClickMe 프론트 전면 개편 — 마스터 체크리스트

> 목표: "기능만 도는 HTML" → **딱 보기만 해도 사로잡히는 실서비스급 UI/UX.** 필요하면 지금과 180° 달라도 됨.
> 진행: 위에서부터 순서대로. 한 항목 끝내면 `[ ]`→`[x]`, 논리 단위로 커밋. 문제(버그·콘솔에러·깨진 링크) 만나면 **바로 고치고** 넘어감.
> 검증: 화면 변경은 반드시 `preview_*`로 직접 띄워 눈으로 확인(스냅샷/스크린샷/콘솔로그). "될 거예요" 금지.

## 불변 규칙 (매 작업 준수)

- [ ] 백엔드 **append-only** — 기존 라우터/서비스/모델 수정·삭제 금지. 새 엔드포인트/테이블/Alembic만 허용.
- [ ] 프론트가 데이터를 기존 API로 못 얻으면 → 기존 걸 고치지 말고 **새 엔드포인트 추가**하고 `docs/frontend-revamp/added-apis.md`에 기록.
- [ ] 기존 기능 동작 0.1도 변경 금지 (순수 UI/UX 레이어만).
- [ ] 넣은 테스트 데이터는 `docs/frontend-revamp/test-data.md`에 기록 → 작업 종료 시 삭제.
- [ ] 새 파일 첫 줄에 역할 한 줄 한국어 헤더 주석.
- [ ] 백엔드 `.py` 건드리면 커밋 전 `cd backend && uv run ruff format . && uv run ruff check . --fix`.
- [ ] 프론트 커밋 전 `cd frontend && pnpm build`(또는 최소 `pnpm lint`) 통과 확인.
- [ ] 커밋 컨벤션 `타입: 한국어 설명` (add/edit/fix/delete), 논리 단위로 자주.

---

## Phase 0 — 디자인 토대 (단독 선행, 전부 이걸 의존)

### 0.0 shadcn 도입
- [x] shadcn 초기화(`components.json` 수동 생성 — init이 globals.css 클로버 방지) — new-york·neutral·CSS변수 방식.
- [x] 의존성 확인/설치: `class-variance-authority`·`tailwind-merge`·`clsx`·`lucide-react`·`tailwindcss-animate`·`framer-motion`·`@radix-ui/*`.
- [x] `lib/utils.ts`에 `cn()` 헬퍼 추가, 경로 alias(`@/*`) 기존 tsconfig 확인.
- [x] 핵심 컴포넌트 설치(20종): button card badge dialog tabs input textarea dropdown-menu tooltip skeleton separator sheet sonner table popover switch avatar progress label scroll-area.
- [x] 기존 커스텀 `ui/`(KpiCard·Select·Pagination) 공존 — **주의: Windows 대소문자 무시로 shadcn `select`가 `Select.tsx` 덮어씀 → 복원함. shadcn select는 충돌로 보류**(커스텀 Select 유지, 후속 마이그레이션 시 리네임).
- [x] shadcn 버튼/카드/배지/스켈레톤/인풋 preview 렌더 확인(라이트·다크 양쪽, /revamp-check).

### 0.1 토큰 체계 (globals.css / shadcn 변수 정렬)
- [x] shadcn CSS 변수 규약(`--background`·`--foreground`·`--card`·`--primary`·`--accent`·`--border`·`--muted`·`--destructive`·`--ring` 등)에 **우리 토큰을 정렬**해서 채운다(shadcn 컴포넌트가 바로 우리 색을 쓰게).
- [x] neutral surface 토큰 확장: `--surface-0`(페이지) `--surface-1`(카드바닥) `--surface-2`(카드) `--surface-3`(팝오버) 라이트/다크 정의.
- [x] text 토큰: `--text-primary` `--text-secondary` `--text-tertiary` `--text-muted` `--text-disabled`.
- [x] border 토큰: `--border` `--border-strong` `--border-stronger`.
- [x] primary 토큰: `--primary`(#3182F6) `--primary-hover` `--primary-subtle`(연한 배경) `--on-primary`.
- [x] accent(포인트) 토큰: `--accent`(#7C3AED 바이올렛) `--accent-subtle` `--on-accent`.
- [x] semantic 토큰 4종(success/warning/danger/info) 각각 fg·`-subtle`(배경)·`-border` 라이트/다크.
- [x] radius scale: `--radius-sm/md/lg/xl`(그리고 카드=12px).
- [x] shadow scale: `--shadow-sm/md/lg`(다크모드 대응).
- [x] focus ring 토큰 정리(기존 `:focus-visible` 유지·토큰화).
- [x] 기존 `--color-*` 변수는 **삭제하지 말고**, 새 이름으로 alias 병행(기존 참조 안 깨지게).

### 0.2 테마 14종 (data-theme)
- [x] `[data-theme]` 레이어 설계: 컬러 테마는 neutrals 공유하고 `--primary`/`--accent`만 override, 에디터다크 3종은 전체 다크 팔레트 override.
- [x] 컬러 11: blue(기본)·indigo·cyan·emerald·orange·mono·wine·violet·rose·amber·teal — 각 primary/accent 헥사 정의(라이트+다크).
- [x] 에디터다크 3: monokai(#272822)·monokai-black(#0A0A0A)·dracula(#282A36) — bg/surface/text/primary/accent 전체 정의.
- [x] 각 테마 라이트/다크 대비(WCAG AA) 자가 점검.

### 0.3 Tailwind 배선 (tailwind.config.ts)
- [x] shadcn init이 넣어준 기본 color 매핑(primary/secondary/accent/muted/destructive/card/border/ring) 확인 — 여기에 우리 추가 토큰(surface-0~3·semantic success/warning/info·text-tertiary 등)을 `var(--...)`로 extend.
- [x] `tailwindcss-animate` 플러그인 등록 확인, `borderRadius`·`boxShadow`·`fontSize`(타이포 스케일) extend.
- [x] 매핑 후 샘플 컴포넌트로 `bg-primary`/`text-secondary`/`bg-success` 실제 먹는지 preview 확인.

### 0.4 테마 프로바이더 & 갤러리
- [x] `ThemeProvider` 확장: 기존 dark/light 토글 유지 + `data-theme` 선택(localStorage 영속) 추가.
- [x] `/themes` 갤러리 페이지: 14테마 × (라이트/다크) 스위처 + 실제 프리미티브(카드·숫자·버튼·배지·차트) 위 렌더.
- [x] 갤러리에서 테마 전환 시 전 컴포넌트 실시간 반영 preview 확인.

### 0.5 공용 프리미티브 (shadcn 위에 우리 토큰 배선)
> shadcn 설치분(0.0)을 기반으로, 없는 것만 조합 컴포넌트로 신설. 전부 우리 토큰을 쓰게.
- [x] `Button` — shadcn 기반, variant(default/secondary/ghost/destructive/outline)·size·loading·icon. 화면당 primary 1개 원칙.
- [x] `Card` — shadcn Card로 통일(header/content/footer).
- [x] `StatCard` — 신설 조합: label·value·unit·delta(증감 색)·optional 스파크라인.
- [x] `Badge`/`Tag` — shadcn Badge + semantic variants(success/warning/danger/info).
- [x] `Section` — 신설: title·description·action 슬롯(섹션 헤더 통일).
- [x] `Input`·`Textarea` — shadcn 설치·검증. **Select은 Windows 파일명 충돌로 shadcn 미설치 → 커스텀 `ui/Select.tsx` 유지**(후속 마이그레이션 시 리네임).
- [x] `Skeleton`(shadcn) 로딩 상태.
- [x] `EmptyState` — 신설: 아이콘·헤드라인·설명·CTA.
- [x] `Tabs`(shadcn) / 필요 시 SegmentedControl.
- [x] `Tooltip`(shadcn).
- [x] `Dialog`/`Sheet`(shadcn) — 모달·드로어.
- [x] `Toast` — shadcn `sonner`로 통일.
- [x] Recharts 공통 테마(색·그리드·툴팁)를 토큰으로 래핑한 차트 프리셋.
- [x] 타이포그래피 스케일 유틸(H1~H3·body·caption) 정리.
- [x] 아이콘: `lucide-react`로 통일(신규 컴포넌트 적용, 기존은 점진 교체 진행).
- 참고: `Tooltip`/`Dialog`/`Sheet`/`Toast(sonner)`는 shadcn 설치 완료(0.0)로 사용 가능, SegmentedControl은 미도입(Tabs로 충분).

---

## Phase 1 — 앱 셸 & 랜딩

### 1.1 셸
- [ ] `framer-motion` 설치(`cd frontend && pnpm add framer-motion`).
- [ ] `AppLayout` 토큰·프리미티브로 리스킨, 여백·정렬 정리.
- [ ] `Sidebar` — 아이콘 일관성, active 인디케이터, hover, 접힘 애니메이션, 그룹 구분.
- [ ] `ProjectPanel`/`CompanyPanel`/`AdminPanel` 토큰화·정돈.
- [ ] 상단바/헤더(있다면) — 검색·알림·프로필·테마토글 정리.
- [ ] 페이지 전환 트랜지션(framer-motion) 도입.
- [ ] 스크롤바·포커스·hover 등 마이크로 인터랙션 통일.

### 1.2 랜딩 `/`
- [ ] Apple식 다이나믹 진입: 히어로 스크롤 리빌·순차 페이드·패럴랙스.
- [ ] 3대 기능(시뮬/생성/매니지먼트) 소개 섹션 재구성.
- [ ] 3단계 프로세스·소셜프루프·CTA 섹션.
- [ ] 로그인 CTA·헤더 정리, 다크모드 대응.
- [ ] 랜딩 반응형 기본 골격(최소 안 깨지게).
- [ ] preview로 스크롤 연출·다크/라이트 확인, 스크린샷.

---

## Phase 2 — 대시보드 (실서비스급 재구성)

> 원칙: 5초 규칙 · 숫자보다 변화(델타) · "지금 할 일" 우선 · 멘탈모델 그룹 · 점진적 공개 · 허영지표 컷 · 역할별 분기 · 활동 피드.

### 2.1 USER 대시보드 `/dashboard`
- [ ] 상단: 인사 + 기간 + primary CTA(새 시뮬레이션).
- [ ] 핵심 KPI 스트립(진행중 캠페인·이번주 시뮬·평균 클릭의향률·승인대기) + 델타.
- [ ] "지금 주목할 것": 이상 감지·리밸런스 제안·승인 대기 alert 카드(semantic).
- [ ] 최근 시뮬레이션 요약(클릭의향률 미니바 + 신뢰구간) → 클릭 시 상세.
- [ ] 주간 지표 추이 차트(Recharts).
- [ ] 최근 활동 피드(시뮬/생성/캠페인).
- [ ] 로딩(Skeleton)·빈 상태(EmptyState)·에러 상태.
- [ ] 데이터 소스 배선: 기존 API 우선, 없으면 신규 엔드포인트 추가 후 `added-apis.md` 기록.

### 2.2 COMPANY 대시보드
- [ ] 팀·프로젝트·직원 관점 요약 KPI + 활동.
- [ ] 로딩/빈/에러 상태.

### 2.3 ADMIN 대시보드 `/admin/dashboard`
- [ ] 시스템·조직·사용 지표 요약, 최근 채팅/생성 로그 요약.
- [ ] 로딩/빈/에러 상태.

---

## Phase 3 — 도메인 화면 (프리미티브로 재구성 + IA 개선 + preview 검증)

### 3.1 시뮬레이션
- [ ] `/simulation` 입력 폼 재구성(단계·검증·프리뷰).
- [ ] 시뮬 결과 뷰(`SimulationResultView`)·리포트 뷰(`SimulationReportView`) 4대 KPI를 분포·신뢰구간 중심으로.
- [ ] 페르소나 반응·토론 패널(`PersonaReactionCard`/`DebatePanel`) 정돈.
- [ ] 개인 딥뷰·세그먼트 비교 뷰 정돈.
- [ ] `/simulations` 내역 리스트(필터·페이지네이션·카드/표).
- [ ] `/simulation/[id]` 상세.
- [ ] 진행 상태(`SimProgress`) 로딩 연출.

### 3.2 생성기
- [ ] `/generator` 입력·시안 3종 결과·기대성과 순위 재구성.
- [ ] `/generations/[id]` 상세.
- [ ] 생성 진행·루프 위젯 정돈.

### 3.3 매니지먼트
- [ ] `/manage` 개요.
- [ ] `/manage/campaigns` 리스트(표·카드·상태배지).
- [ ] `/manage/campaigns/new` 생성 폼.
- [ ] 캠페인 상세(`CampaignDetail`·차트·퍼널·도넛).
- [ ] `/manage/monitoring` 모니터링(헬스·스파크라인·차트).
- [ ] `/manage/anomaly` 이상 감지.
- [ ] `/manage/budget` 예산(게이지·도넛).
- [ ] `/manage/compare` 비교(리프트 보드/차트).
- [ ] `/manage/connect` 연동.
- [ ] `/manage/reliability` 신뢰도.
- [ ] 승인/집행 관련 카드(`ApprovalBridge`·`AuditTimeline`) 정돈(모드 배지 유지).

### 3.4 프로젝트·조직·프로필
- [ ] `/projects`·`/projects/[id]`.
- [ ] `/my-org`.
- [ ] `/profile`.
- [ ] `/trash`.

### 3.5 채팅 (약 30개 위젯)
- [ ] `ChatConversation`·`ChatRouteView`·컨트롤러 셸 토큰화.
- [ ] 입력창·메시지 버블·스트리밍 커서 정돈.
- [ ] 시뮬/생성/분석/비교/토론 위젯들 카드 스타일 통일(토큰).
- [ ] 승인·액션 카드류 정돈.
- [ ] 알림/채팅 센터(`Center`·`AlarmCenter`·`ChatCenter`) 정돈.

### 3.6 관리자 (9)
- [ ] `/admin/dashboard`(2.3와 연계)·organizations·manage-user·companies·generations·chats·chat-log·inquiry·check.

### 3.7 기업 계정 (5)
- [ ] `/company/teams`·projects·members·generations·chats.

### 3.8 결제 · 인증 · 법적
- [ ] `/payment`·success·fail (TossPayments UI 정돈, 동작 불변).
- [ ] `/sign-in` 로그인.
- [ ] `/privacy`·`/terms`·`/data-deletion` 타이포·가독성 정돈.

---

## Phase 4 — 반응형 (개편 후)

- [ ] breakpoint 전략 확정(sm/md/lg/xl) 및 문서화.
- [ ] 셸: 사이드바 드로어·좌측 패널 모바일 동작 정교화.
- [ ] 대시보드: KPI/카드 리플로우(모바일 1열).
- [ ] 표 → 모바일 카드 변환 패턴.
- [ ] 터치 타깃(44px)·폼·모달 모바일 최적화.
- [ ] 태블릿(md) 레이아웃 최적화.
- [ ] 주요 화면 각 breakpoint preview 확인(리사이즈·스크린샷).

---

## Phase 5 — 크로스커팅 QA & 마감

- [ ] **하드코딩 색 sweep**: 헥사·`bg-blue-500` 류를 토큰/유틸로 교체(2747+233 지점, 화면 작업하며 점진 처리 후 잔여 grep 정리).
- [ ] 다크모드 전 화면 점검(대비·투명도·경계).
- [ ] 접근성: focus-visible·aria-label·대비·키보드 내비.
- [ ] 콘솔 에러·경고 0 만들기(preview_console_logs).
- [ ] 깨진 링크·라우팅·404 점검.
- [ ] 아이콘 세트 일관성.
- [ ] 로딩/빈/에러 상태 누락 화면 보완.
- [ ] `pnpm build` 통과, ESLint 클린.
- [ ] 새 라우트 생겼으면 `backend/scripts/gen_docs.py`로 문서 갱신(직접 수정 금지).
- [ ] `added-apis.md`·`test-data.md` 최종 점검 — 테스트 데이터 전부 삭제됐는지 확인.
- [ ] 최종 데모 플로우 preview로 통주행(랜딩→로그인→대시보드→시뮬→매니지먼트) 스크린샷.

---

## Phase 6 — 전체 완료 시 통합 (위 모든 항목이 `[x]`가 된 뒤에만)

> **가드**: Phase 0~5의 모든 `[ ]`가 `[x]`가 되기 전에는 이 단계를 실행하지 않는다.

- [ ] `git status`로 **워킹트리가 깨끗한지**(스테이징/변경/untracked 남은 것 없음) 확인. 남은 변경이 있으면 먼저 논리 단위로 커밋해 워킹트리를 비운다.
- [ ] 워킹트리가 완전히 비어 있으면 아래를 순서대로 실행해 `feat/front-fix`를 `feat/simulation-doyeon`에 통합한다.

```bash
git push
git checkout feat/simulation-doyeon
git merge feat/front-fix
git push
git branch -d feat/front-fix
git push origin --delete feat/front-fix
```

- [ ] 병합 충돌이 나면 자동 해결하지 말고 **멈춰서 보고**. 워킹트리가 비어 있지 않으면 병합을 실행하지 말고 멈춘다.

---

## 진행 로그 (루프가 여기 이어서 기록)

- (예: 2026-07-08 P0.1 토큰 확장 완료 — commit abc123)
- 2026-07-08 P0.0 shadcn 도입 완료 — 20종 컴포넌트 설치, cn() 헬퍼, components.json 수동 생성. Windows 대소문자 충돌로 커스텀 Select 덮어써진 것 복원, shadcn select 보류.
- 2026-07-08 P0.1/0.3 토큰 체계+Tailwind 배선 완료 — RGB 채널 토큰(surface0~3·ink 텍스트·line 보더·primary·point(브랜드 바이올렛, shadcn accent와 분리)·semantic 4종), 라이트/다크 정의. 기존 --color-* alias 유지. preview 라이트·다크 검증(primary=#3182F6 확인), pnpm build 통과.
- 2026-07-08 P0.2 테마 14종 완료 — themes.css(html[data-theme] specificity로 :root override). 컬러11은 primary/point만, 에디터다크3(monokai/monokai-black/dracula)은 전체 팔레트. eval 검증: blue→emerald(16 185 129)→rose→monokai(bg #272822·다크강제) 실시간 전환 확인.
- 2026-07-08 P0.4 ThemeProvider 확장+/themes 갤러리 완료 — data-theme localStorage 영속·에디터테마 다크강제, layout 인라인스크립트 FOUC 방지. 갤러리에서 14테마 스위처+프리미티브 실시간 반영 검증(콘솔 에러 0). ※ preview_screenshot은 이 환경에서 외부 폰트 CDN network-idle 대기로 타임아웃 → snapshot/inspect/eval로 검증 대체.
- 2026-07-08 P0.5 공용 프리미티브 완료 — StatCard(델타색·스파크라인)·Section·EmptyState 신설, chart-theme 훅(테마색 Recharts), 타이포 유틸(.text-h1~caption). shadcn 20종 활용. Select은 파일명 충돌로 커스텀 유지.
