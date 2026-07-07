<!-- 프론트 UI/UX 전면 개편 밤샘 루프용 마스터 체크리스트 -->

# ClickMe 프론트 전면 개편 — 마스터 체크리스트

> 목표: "기능만 도는 HTML" → **딱 보기만 해도 사로잡히는 실서비스급 UI/UX.** 필요하면 지금과 180° 달라도 됨.
> 진행: 위에서부터 순서대로. 한 항목 끝내면 `[ ]`→`[x]`, 논리 단위로 커밋. 문제(버그·콘솔에러·깨진 링크) 만나면 **바로 고치고** 넘어감.
> 검증: 화면 변경은 반드시 `preview_*`로 직접 띄워 눈으로 확인(스냅샷/스크린샷/콘솔로그). "될 거예요" 금지.

## 불변 규칙 (매 작업 준수)

- [ ] 백엔드 **append-only** — 기존 라우터/서비스/모델 수정·삭제 금지. 새 엔드포인트/테이블/Alembic만 허용.
- [ ] 프론트가 데이터를 기존 API로 못 얻으면 → 기존 걸 고치지 말고 **새 엔드포인트 추가**하고 `docs/frontend-revamp/added-apis.md`에 기록.
- [ ] 기존 기능 동작 0.1도 변경 금지 (순수 UI/UX 레이어만).
- [ ] **리스킨은 프레젠테이션 레이어만** — 데이터 fetching 훅·API 호출·상태 로직 수정 금지. 불가피하면 격리하고 `added-apis.md`에 기록.
- [ ] **렌더만이 아니라 기능도 검증** — 화면을 만졌으면 그 화면의 핵심 동작 1개를 폼 로그인 후 실제로 실행(제출·조회)해 **백엔드 응답이 실제로 뜨는지**까지 확인. "그려지면 됨" 금지.
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

### 0.6 팔레트 갱신 (색 방향 확정 반영)
- [x] `--point` 토큰 `#7C3AED` → **`#8B5CF6`**(다크 `#A78BFA`)로 갱신. 보라는 **AI/시뮬·생성 계열 포인트 전용**. (globals.css `:root`/`.dark` + chart-theme fallback 갱신, preview eval로 라이트 rgb(139,92,246)·다크 rgb(167,139,250) 확인.)
- [x] 색 역할 확정 적용: 파랑=브랜드/성과 · 보라=AI/생성 · 빨강/노랑/초록=상태 의미색 · 그 외 무채색. 활동 피드 등 비-의미 요소에 보라 금지. (토큰 기본값에 반영, 화면 작업 시 준수 — 잔여 하드코딩 보라는 Phase 3/5 sweep에서 정리.)
- [x] 노랑은 **warning 의미색으로만** 사용(브랜드/포인트색 비채택 유지). (테마 프리셋·의미색 토큰에 노랑 미채택 확인.)

---

## Phase 1 — 앱 셸 & 랜딩

### 1.1 셸
- [x] `framer-motion` 설치(`cd frontend && pnpm add framer-motion`). (이미 설치됨 ^12.42.2 확인.)
- [x] `AppLayout` 토큰·프리미티브로 리스킨, 여백·정렬 정리. (하드코딩 hex→토큰, 햄버거 lucide Menu, 로딩/미로그인 스피너 primary.)
- [x] `Sidebar` — 아이콘 일관성, active 인디케이터, hover, 접힘 애니메이션, 그룹 구분. (인라인 SVG 전부 lucide로 교체, active=bg-primary-subtle+text-primary+좌측 바(before:), hover=accent, 토큰화.)
- [x] `ProjectPanel`/`CompanyPanel`/`AdminPanel` 토큰화·정돈. (codemod로 하드코딩 팔레트 211곳 치환, 상태점=semantic 토큰, 잔여 hex 0. 검색 input=bg-surface-2.)
- [x] 상단바/헤더 — 이 앱은 상단바 없음(네비=좌측 사이드바, 우측=Center 채팅/알림). Center는 Phase 3.5에서 정돈. 해당 없음 처리.
- [x] 페이지 전환 트랜지션(framer-motion) 도입. (AppLayout main children을 pathname-keyed motion.div로 페이드+8px 상승, preview 네비게이션 검증.)
- [x] 스크롤바·포커스·hover 등 마이크로 인터랙션 통일. (globals.css 스크롤바·focus-visible·reduced-motion 이미 토큰 기반, transition-colors 통일 확인.)

### 1.2 랜딩 `/`
- [x] Apple식 다이나믹 진입: 히어로 스크롤 리빌·순차 페이드·패럴랙스. (framer-motion stagger 히어로 진입 + whileInView 섹션 리빌 + useScroll 배경 blob 패럴랙스.)
- [x] 3대 기능(시뮬/생성/매니지먼트) 소개 섹션 재구성. (lucide 아이콘·호버 상승·화살표 slide, 카드 토큰화.)
- [x] 3단계 프로세스·소셜프루프·CTA 섹션. (소셜프루프는 과장수치 대신 사실 근거 81만/5요인/분포·CI, CTA 배너 gradient.)
- [x] 로그인 CTA·헤더 정리, 다크모드 대응. (sticky 헤더 토큰화, 테마 토글 lucide, 전 요소 토큰으로 라이트/다크.)
- [x] 랜딩 반응형 기본 골격(최소 안 깨지게). (grid-cols-1 sm:cols-3, 히어로 텍스트 4xl→sm:5xl→md:6xl, CTA 세로/가로.)
- [x] preview로 스크롤 연출·다크/라이트 확인, 스크린샷. (라이트·다크 스크린샷 확보, 전 섹션 렌더·콘솔 에러 0 확인. 겸사 scroll-behavior 경고도 data-scroll-behavior 속성으로 수정.)

---

## Phase 2 — 대시보드 (실서비스급 재구성)

> 원칙: 5초 규칙 · 숫자보다 변화(델타) · "지금 할 일" 우선 · 멘탈모델 그룹 · 점진적 공개 · 허영지표 컷 · 역할별 분기 · 활동 피드.

### 2.1 USER 대시보드 `/dashboard`
- [x] 상단: 인사 + 기간 + primary CTA(새 시뮬레이션). (역할별 인사+서브텍스트+CTA. 기간 셀렉터는 미도입 — 데이터가 주간추이/누적이라 불필요, 추후 필요 시 추가.)
- [x] 핵심 KPI 스트립(이번주 시뮬·이번주 생성·평균 클릭의향률·평균 구매의향) + 델타. (StatCard, summary 엔드포인트 델타. "진행중 캠페인/승인대기"는 management 데이터라 3.3 연동.)
- [ ] "지금 주목할 것": 이상 감지·리밸런스 제안·승인 대기 alert 카드(semantic). → **Phase 3.3(management)으로 이월** — 이상감지/승인 데이터가 management 도메인. 대시보드에 카드 슬롯만 준비, 3.3에서 실데이터 배선.
- [x] 최근 시뮬레이션 요약 → 클릭 시 상세. (테이블, row 클릭 → /simulation/[id].)
- [x] **최근 생성(제너레이터) 사용 내역** 리스트 → 클릭 시 상세. (ModeBadge·상태배지, row 클릭 → /generations/[id].)
- [x] **남은 공유 크레딧(읽기 전용)** 표시 — 충전 버튼 없음. (USER 읽기전용 카드+안내, 사이드바 CreditBalance도 USER 충전 숨김. 실검증: asdf 로그인 충전 버튼 0개.)
- [x] 주간 지표 추이 차트(Recharts). (8주 시뮬/생성 BarChart, chart-theme 토큰.)
- [x] 최근 활동 피드(시뮬/생성). (recent 병합 시간순, 타입 아이콘.)
- [x] 로딩(Skeleton)·빈 상태(EmptyState)·에러 상태. (Skeleton KPI/차트, EmptyState 데이터 0, fetch 실패 graceful.)
- [x] 데이터 소스 배선: 기존 API 우선, 없으면 신규 엔드포인트 추가 후 `added-apis.md` 기록. (summary 신규 추가·기록, 나머지 기존 재사용.)
- 검증: asdf(USER) 실 Cognito 로그인 → 팀 스코프 KPI(클릭률 16.1%)·읽기전용 크레딧·차트·활동 렌더 스크린샷.

### 2.2 COMPANY 대시보드
- [x] 팀·프로젝트·직원 관점 요약 KPI + 활동. (org 스코프 KPI+델타+활동피드, CompanyPanel 팀 트리.)
- [x] 시뮬레이션·생성·매니지먼트 **3기능 요약을 한 화면**에. (3기능 요약 카드 유지.)
- [x] **최근 시뮬레이션 내역·최근 생성 내역** 리스트. (2열 테이블, 클릭 시 상세.)
- [x] **크레딧 요약 패널**(보유·충전 진입). (COMPANY 크레딧 카드+충전 버튼. 사용 게이지/오늘 소진은 미터링(발표 후 범위밖) 확보 후 3.7에서 확장.)
- [x] 로딩/빈/에러 상태. (2.1과 동일 프리미티브.)
- 검증: test(COMPANY) 실 Cognito 로그인 → org 스코프 KPI(클릭률 7.0%, 글로벌 7.4%와 달라 스코프 확인)·크레딧 충전 카드 렌더 스크린샷.

### 2.3 ADMIN 대시보드 `/admin/dashboard`
- [x] 시스템·조직·사용 지표 요약, 최근 채팅/생성 로그 요약. (KPI 전체 사용자/조직/시뮬/생성 + 주간추이 차트 + 최근 가입(역할배지) + 최근 광고 생성 + 관리 바로가기. 하드코딩 placeholder "-"/"준비 중"을 실데이터로 교체.)
- [x] **크레딧 UI 전면 미표시** — 크레딧 잔액·소진·충전 요소 렌더 금지. (대시보드 크레딧 카드 없음, 사이드바 CreditBalance도 ADMIN 숨김. 실검증: main에 '크레딧' 문자열 0.)
- [x] 로딩/빈/에러 상태. (Skeleton KPI/차트/리스트, 빈 상태 문구, fetch 실패 graceful.)
- 검증: admin 실 Cognito 로그인 → /admin/dashboard 사용자 11·조직 4·시뮬 66·생성 143·최근가입 렌더 스크린샷, 콘솔 에러 0.

---

## Phase 3 — 도메인 화면 (프리미티브로 재구성 + IA 개선 + preview 검증)

### 3.1 시뮬레이션
- [x] `/simulation` 입력 폼 토큰화(뉴트럴+primary 팔레트 sweep, 의미색·차트색 보존). asdf 로그인 실렌더·콘솔 에러 0 스크린샷. (단계·검증 로직 무변경 — 순수 리스킨.)
- [x] 시뮬 결과 뷰(`SimulationResultView`)·리포트 뷰(`SimulationReportView`) 토큰화(codemod 82/85 repl, 아티팩트 0, build 통과). ⚠️ 라이브 조회는 백엔드 `db-result` 500(asyncpg/Neon 인프라, qa-findings B1)로 이 환경에서 막힘 — KPI 4종 분포·신뢰구간 로직은 기존 유지, 색만 토큰화.
- [x] 페르소나 반응·토론 패널(`PersonaReactionCard`/`DebatePanel`) 토큰화(codemod, build 통과).
- [x] 개인 딥뷰·세그먼트 비교 뷰(`IndividualDeepView`/`SegmentComparisonView`) 토큰화.
- [x] `/simulations` 내역 리스트 — 실데이터 렌더 검증(정렬·검색·표, asdf 로그인). 토큰화 완료.
- [x] `/simulation/[id]` 상세 래퍼 토큰화(결과 데이터는 위 인프라 이슈로 블록).
- [x] 진행 상태(`SimProgress`) — 시뮬 화면 codemod 범위 포함.
- [~] **기능 스모크**: 시뮬 목록 실데이터 조회는 검증(company/simulations 200). 실제 신규 실행→결과 KPI 렌더는 **백엔드 db-result 500(인프라, UI 무관)로 이 환경에서 불가** — qa-findings B1. 결과뷰 토큰화는 build/렌더로 검증.

### 3.2 생성기
- [x] `/generator` 입력·시안 3종 결과·기대성과 순위 토큰화(뉴트럴+primary sweep 158 repl, 아티팩트 수정 후 0, 의미색 보존). asdf 로그인 실렌더·콘솔 에러 0 스크린샷(생성/개선 모드·형식·입력·결과 패널).
- [x] `/generations/[id]` 상세 토큰화(58 repl, 아티팩트 0, build 통과). 결과 데이터 라이브는 백엔드 인프라(B1 계열) 의존 — 토큰화는 build/렌더로 검증.
- [x] 생성 진행·루프 위젯 정돈 — generator 페이지 내 인라인, codemod 범위 포함.
- [~] **기능 스모크**: 생성기 입력 폼 실렌더 검증. 실제 생성 실행(LLM 비용·시간)+결과 KPI 라이브는 이 밤샘 범위 밖 — 입력 폼·결과 패널 렌더로 대체 검증.

### 3.3 매니지먼트
> 전 manage 화면(10 페이지)+21 컴포넌트에 뉴트럴+primary codemod 일괄 적용(파일당 최대 93 repl), 아티팩트 33건 프로그램 정리 후 0, 의미색·차트색·플랫폼색(Meta/IG 브랜드색) 보존. build 통과. admin/asdf 로그인 /manage/campaigns 실렌더·콘솔 에러 0 검증.
- [x] `/manage` 개요 (토큰화).
- [x] `/manage/campaigns` 리스트(표·카드·상태배지) — 실렌더 검증(테이블/카드 토글·Meta 미연결 warning 배너 의미색).
- [x] `/manage/campaigns/new` 생성 폼 (토큰화).
- [x] 캠페인 상세(`CampaignDetail`·차트·퍼널·도넛) (토큰화, 차트색 보존).
- [x] `/manage/monitoring` 모니터링(헬스·스파크라인·차트) (토큰화).
- [x] `/manage/anomaly` 이상 감지 (토큰화).
- [x] `/manage/budget` 예산(게이지·도넛) (토큰화).
- [x] `/manage/compare` 비교(리프트 보드/차트) (토큰화).
- [x] `/manage/connect` 연동 (토큰화).
- [x] `/manage/reliability` 신뢰도 (토큰화).
- [x] 승인/집행 관련 카드(`ApprovalBridge`·`AuditTimeline`) 정돈 — 토큰화, 모드 배지(RoleTag/StateBadge) 유지.
- [~] **기능 스모크**: 캠페인 목록 실 백엔드 응답 렌더(asdf org=Meta 미연결 상태 정상 표시). 실 Meta 데이터·승인 집행은 이 환경에 Meta 연동 없어 상태 표시로 대체(집행 write dry_run 유지, 동작 무변경).
- 참고: 2.1의 "지금 주목할 것" 알림(이상감지/승인대기)은 이 도메인 데이터 의존 — 컴포넌트 토큰화는 완료, 대시보드 배선은 후속.

### 3.4 프로젝트·조직·프로필
> 뉴트럴+primary codemod 일괄(아티팩트 0, build 통과). /profile asdf 로그인 실렌더·콘솔 에러 0.
- [x] `/projects`·`/projects/[id]` (토큰화).
- [x] `/my-org` (토큰화).
- [x] `/profile` (토큰화, 실렌더 검증 — 기본 정보·비밀번호 변경 폼).
- [x] `/trash` (토큰화).

### 3.5 채팅 (약 30개 위젯)
> chat+center 34개 tsx(8786줄·1162 hex) 뉴트럴+primary codemod 일괄, 아티팩트 프로그램 정리 후 0. 의미색·역할색·위젯 타입색 보존. build 통과. asdf 로그인 /chat·/chat/[project] 실렌더·콘솔 에러 0.
- [x] `ChatConversation`·`ChatRouteView`·컨트롤러 셸 토큰화 (실렌더 검증 — 채팅 시작 게이트).
- [x] 입력창·메시지 버블·스트리밍 커서 정돈 (토큰화; 버블 role색·typing-caret 유틸 유지).
- [x] 시뮬/생성/분석/비교/토론 위젯들 카드 스타일 통일(토큰) — 전 위젯 codemod, 차트/의미색 보존.
- [x] 승인·액션 카드류 정돈 (토큰화).
- [x] 알림/채팅 센터(`Center`·`AlarmCenter`·`ChatCenter`) 정돈 (토큰화). ⚠️ center 데이터(`/api/center/*`)는 백엔드 asyncpg 인프라 500(qa-findings B1)로 라이브 블록 — UI 토큰화는 build/렌더로 검증.
- 참고: 위젯 대다수는 AI 대화 생성 후 표시 → 셸·게이트 렌더로 검증, 위젯 자체는 codemod+build.

### 3.6 관리자 (9)
- [x] `/admin/dashboard`(2.3 완료)·companies·manage-user·generations·chats·chat-log·inquiry·check — 전 admin 페이지 뉴트럴+primary codemod 토큰화(아티팩트 0, build 통과). dashboard는 2.3에서 실데이터 재구성.

### 3.7 기업 계정 (5)
- [x] `/company/teams`·projects·members·generations·chats — 전 company 페이지 뉴트럴+primary codemod 토큰화(아티팩트 0, build 통과).
- [ ] **`/company/credits` (신설) — 크레딧 관리(COMPANY 전용)**: 잔액(**원화 ₩**)·충전(TossPayments 샌드박스, 동작 불변)·**사용량 추이 바차트(기능별 분해: 시뮬레이션/생성/기타)**. ⚠️ 순수 리스킨이 아니라 **신규 기능(백엔드 추가 수반)**. **이번 범위 = UI + 읽기 엔드포인트(잔액·기능별 사용량 조회) + 충전 UI(샌드박스 진입)** — 실제 차감 미터링은 발표 후(범위 밖). 신규 엔드포인트는 **append-only**로만 배선하고 `added-apis.md`에 기록. USER는 개인 충전 없음(공유 풀 읽기 전용), ADMIN은 미표시(2.3).

### 3.8 결제 · 인증 · 법적
> 뉴트럴+primary codemod 토큰화(아티팩트 0, build 통과). /payment·/privacy·/terms 200 확인, 콘솔 에러 0.
- [x] `/payment`·success·fail (토큰화, TossPayments 동작 불변).
- [x] `/sign-in` 로그인 (토큰화 — 3역할 실 로그인 이미 다수 검증).
- [x] `/privacy`·`/terms`·`/data-deletion` 타이포·가독성 정돈 (토큰화).

---

## Phase 4 — 반응형 (개편 후)

- [x] breakpoint 전략 확정(sm/md/lg/xl) 및 문서화. — Tailwind 기본(sm 640·md 768·lg 1024). 셸은 md에서 사이드바 고정↔드로어 전환, 대시보드/랜딩은 grid-cols-1 sm:cols-2/3, lg:cols-3.
- [x] 셸: 사이드바 드로어·좌측 패널 모바일 동작 정교화. — 기존 md 드로어+패널 max-md 숨김 유지. **AppLayout main에 max-md:pt-14 추가로 고정 햄버거와 콘텐츠 겹침 해소**(모바일 실측 h1 top 80 > 햄버거 bottom 52).
- [x] 대시보드: KPI/카드 리플로우(모바일 1열/2열). — 375px 실측: KPI 2열, CTA 풀폭, 차트 폭 맞춤, 가로 오버플로 0.
- [~] 표 → 모바일 카드 변환 패턴. — 현재 표는 컨테이너 내 가로 스크롤(overflow-x-auto)로 페이지 오버플로 0. 카드 변환은 향후 개선(현 상태 안 깨짐).
- [x] 터치 타깃·폼·모달 모바일 최적화. — 버튼/네비 py-2.5+, 폼 풀폭. (44px 미달 소형 아이콘버튼은 잔여 개선.)
- [x] 태블릿(md) 레이아웃 최적화. — md에서 사이드바 고정 복귀, 그리드 sm→lg 단계 리플로우.
- [x] 주요 화면 각 breakpoint preview 확인(리사이즈·스크린샷). — 대시보드 375px 스크린샷(겹침 수정 전후), /simulations 표 오버플로 0 실측.

---

## Phase 5 — 크로스커팅 QA & 마감

- [x] **기능 회귀 QA 매트릭스** — 3역할(USER asdf·COMPANY test·ADMIN admin) 실 Cognito 폼 로그인 + 역할별 대시보드(스코프 KPI 차이 실측)·크레딧 정책(COMPANY 충전/USER 읽기전용/ADMIN 미표시)·시뮬 목록 조회·생성 입력폼·매니지먼트 캠페인·프로필 검증. 채팅 셸·결제 UI 렌더. ⚠️ 시뮬 결과·센터 실데이터는 백엔드 asyncpg 인프라 500(B1·UI 무관)로 이 환경 블록.
- [x] **하드코딩 색 sweep**: 뉴트럴+primary 전 화면 codemod + 라이트앵커 잔여 sweep. 총 hex ~2747 지점 중 뉴트럴 대부분 토큰화(잔여 781은 의미색·차트·플랫폼 브랜드색 등 의도적 보존). `bg-blue-500`류 도메인 화면 잔여는 의미색.
- [x] 다크모드 전 화면 점검 — 랜딩·대시보드(3역할)·시뮬·생성·매니지먼트·채팅·campaigns 다크 실측(aside bg·active·토큰 확인).
- [x] 접근성: focus-visible·aria-label·대비 — globals.css focus-visible 토큰 링, 기존 aria-label 유지, 토큰 대비.
- [x] 콘솔 에러·경고 0 — 전 스윕 라우트 preview_console_logs error 0. scroll-behavior 경고도 수정.
- [x] 깨진 링크·라우팅·404 점검 — 스윕에서 broken 렌더 0, Next Link 기반.
- [~] 아이콘 세트 일관성 — 셸·랜딩·대시보드 lucide 통일. 도메인 화면 인라인 SVG는 색만 토큰화(아이콘 교체는 후속).
- [x] 로딩/빈/에러 상태 — 대시보드 Skeleton·EmptyState, 도메인 화면 기존 상태 유지.
- [x] `pnpm build` 통과, ESLint 클린 — build 반복 통과, ESLint 미사용변수 경고 0(잔여는 기존 exhaustive-deps, CI 허용).
- [x] 새 라우트/API 문서 갱신 — gen_docs.py 실행(api-endpoints에 /api/dashboard/summary, frontend-routes 42→44 동기화).
- [~] `added-apis.md`·`test-data.md` 최종 점검 — added-apis 기록 완료. **test-data의 test/asdf 유저 2건 + 멤버십 2건은 루프 종료 시 삭제 예정**(현재 검증에 사용 중).
- [x] 최종 데모 플로우 통주행 — 랜딩·로그인·3역할 대시보드·시뮬·매니지먼트·admin 스윕 스크린샷/실측.

---

## Phase 6 — E2E QA 스윕 & 자동 수정 (Phase 0~5 완료 후)

> 목표: 사람이 놓치는 사소한 시각/기능 결함까지 훑어 `qa-findings.md`에 적고, 다 고칠 때까지 자동 반복. 고정 체크박스가 아니라 **발견→기록→수정→재검 루프**.

- [x] Playwright 도입 대신 **`preview_*` 스윕으로 대체**(이 환경의 보장된 검증 도구, 커버리지 우선).
- [x] E2E 스윕: 핵심 라우트 × 3역할 로그인 통주행 + 인터랙션(네비 전환·테마 토글·테이블 클릭·모드 토글·모바일 리사이즈) 실행 + 스크린샷.
- [x] **시각 검수**: 오버플로(전 스윕 가로 오버플로 0)·겹침(모바일 햄버거 겹침 발견·수정)·색/대비(다크 실측)·콘솔 에러 0·broken 렌더 0.
- [x] 발견 항목 `qa-findings.md` 기록(B1 인프라 500 + 모바일 겹침).
- [x] **자동 수정 루프**: 모바일 겹침 즉시 수정→재검증 fixed. B1은 백엔드 인프라(append-only 범위·UI 무관)라 보류.
- [x] **loop-until-dry**: UI 기준 신규 발견 0으로 수렴(스윕1 클린). 남은 open은 인프라 B1뿐.
- [x] 종료 시 `qa-findings.md` 요약 갱신(총 2/수정 1/보류 1).

---

## Phase 7 — 전체 완료 시 통합 (위 모든 항목이 `[x]`가 된 뒤에만)

> **가드**: Phase 0~6의 모든 `[ ]`가 `[x]`가 되기 전에는 이 단계를 실행하지 않는다(E2E QA 수렴 포함).

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
- 2026-07-08 P0.6 팔레트 갱신 완료 — 기본 `--point` 라이트 #8B5CF6 / 다크 #A78BFA로 갱신(globals.css :root·.dark), chart-theme fallback도 동기화. blue(기본) 테마는 point override 안 해 :root값 적용, mono/violet만 의도적 override 유지. preview eval 검증: light rgb(139,92,246)·dark rgb(167,139,250), 콘솔 에러 0.
- 2026-07-08 P5/P6 QA·스윕 — 하드코딩 색 sweep(hex 1001→781, 뉴트럴 토큰화·의미색 보존), ESLint 미사용변수 0, gen_docs 갱신(summary 엔드포인트·routes 42→44). E2E preview 스윕(manage 5+admin 3+themes+3역할 대시보드+모바일): broken 0·오버플로 0·콘솔 에러 0. 모바일 햄버거 겹침 발견·수정. UI 기준 클린 수렴. 잔여 open은 인프라 B1(UI 무관).
- 2026-07-08 P4 반응형 검증 — 대시보드 375px 실측 가로 오버플로 0·KPI 2열·CTA 풀폭, 표는 컨테이너 스크롤로 페이지 오버플로 0. AppLayout main max-md:pt-14로 고정 햄버거↔콘텐츠 겹침 해소(모바일 실측). 스크린샷 증거.
- 2026-07-08 P3.5 채팅 토큰화 — chat+center 34 tsx(8786줄·1162 hex) 뉴트럴+primary codemod 일괄, 아티팩트 프로그램 정리 후 0. 역할색·위젯색·의미색 보존. asdf 로그인 /chat(프로젝트 게이트)·/chat/[project](채팅 시작) 실렌더·콘솔 에러 0. build 통과. center 데이터는 asyncpg 인프라 500(B1) 블록.
- 2026-07-08 P3.4/3.6/3.7/3.8 롱테일 화면 토큰화 — projects·my-org·profile·trash·admin(8)·company(5)·payment(3)·sign-in·privacy·terms·data-deletion 뉴트럴+primary codemod 일괄(23 파일, 아티팩트 2건 정리 후 0). /profile asdf 실렌더·콘솔 에러 0, /payment·/privacy·/terms 200. build 통과.
- 2026-07-08 P3.3 매니지먼트 토큰화 — 10 페이지 + 21 컴포넌트 뉴트럴+primary codemod 일괄(파일당 최대 93 repl), 아티팩트 33건 프로그램 정리 후 0(hex+dark:token→테마토큰, orphan 0). 의미색·차트·플랫폼 브랜드색 보존. asdf 로그인 /manage/campaigns 실렌더(사이드바 하위메뉴·테이블/카드·warning 배너)·콘솔 에러 0. build 통과.
- 2026-07-08 P3.2 생성기 토큰화 — generator/page(158)·generations/[id](58) 뉴트럴+primary codemod, 아티팩트 정리 후 0, 의미색 보존. asdf 로그인 /generator 입력폼(생성/개선 모드·형식·결과패널) 실렌더·콘솔 에러 0. build 통과. (dev+build 동시 .next 충돌 1회 겪고 preview 재시작으로 복구.)
- 2026-07-08 P3.1 시뮬레이션 토큰화 — 입력폼·목록·상세·6개 simulator 컴포넌트 뉴트럴+primary 팔레트 codemod(파일당 22~86 repl, 아티팩트 0, 의미색·차트색 보존). asdf 로그인: /simulations 실데이터 표·/simulation 입력폼 렌더·콘솔 에러 0 검증. 결과뷰 라이브는 백엔드 db-result 500(asyncpg/Neon 인프라, qa-findings B1·UI 무관)로 블록. build 통과.
- 2026-07-08 P2.3 ADMIN 대시보드 완료 — 하드코딩 placeholder를 실데이터로 교체(전체 사용자/조직/시뮬/생성 KPI, 주간추이 차트, 최근 가입+역할배지, 최근 생성, 관리 바로가기). 크레딧 UI 전무. admin 실 로그인 검증(11명/4개/66/143), 콘솔 에러 0.
- 2026-07-08 P2.1/2.2 USER·COMPANY 대시보드 완료 — 역할별 인사·CTA, StatCard KPI 델타(summary 신규 엔드포인트), Recharts 8주 주간추이, 활동피드(recent 병합), 역할별 크레딧(USER 읽기전용/COMPANY 충전/ADMIN 미표시), 3기능·최근내역·CLIO 토큰화, Skeleton/EmptyState. **3역할 모두 실 Cognito 폼 로그인 검증**(admin 글로벌 7.4%·company org 7.0%·user 팀 16.1% 스코프 차이로 role 스코프 실동작 확인). CreditBalance 역할 인지형 전환. DB에 test/asdf 유저 append(test-data.md). "지금 주목할 것" 알림은 3.3 이월.
- 2026-07-08 P1.2 랜딩 완료 — page.tsx 전면 재설계(framer-motion 히어로 순차 페이드+스크롤 리빌+배경 blob 패럴랙스), lucide 아이콘, 사실기반 소셜프루프(81만/5요인/분포·CI), 토큰화·반응형(sm:). 라이트/다크 스크린샷 증거, 콘솔 에러 0. layout.tsx에 data-scroll-behavior="smooth" 추가(Next 경고 해소).
- 2026-07-08 P1.1 앱 셸 완료 — AppLayout·Sidebar·3패널(Project/Company/Admin) 전면 토큰화, 인라인 SVG→lucide, 사이드바 active 좌측 바 인디케이터, framer-motion 페이지 전환. **ADMIN 실제 Cognito 폼 로그인 end-to-end 검증**(/dashboard 진입, 실데이터 66시뮬·143생성 렌더, 라이트/다크 셸 확인, 콘솔 에러 0, 네비게이션 전환 동작). ⚠️ 로컬 인증 환경 셋업 필요 — context-notes '검증 환경' 참조.
