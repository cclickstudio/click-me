# 개편 체크리스트 — 페이지별 작업 · 우선순위 · 워크트리 분할

> 병합 후 착수할 실제 작업 목록. 각 페이지의 반응형 깨짐 지점과 개편 항목을 정리했다.
> `[ ]` 미착수 / `[~]` 진행 / `[x]` 완료. 페이지 추가·삭제·경로 변경 시 `backend/scripts/gen_docs.py` 재실행.

## 0. 기반 작업 (Phase 0 — 병합 직후, 병렬 불가·먼저)

- [ ] `globals.css` 토큰 확장(상태색 success/warning/danger/info, surface-2, chart-1~6) — [design-system.md](./design-system.md) §1.3
- [ ] `tailwind.config.ts` 시맨틱 컬러 매핑 추가 — §1.4 (네이밍 별칭 `fg`/`primary` 확정)
- [ ] opacity modifier 필요 여부 판단 → 채널 방식 전환 결정
- [ ] `hooks/useMediaQuery.ts` + `useIsMobile` 신설
- [ ] (도입 시) shadcn/ui init + 기본 컴포넌트(Button/Card/Dialog/Sheet/Select/Tabs/Table/Toast) 도입·토큰 매핑
- [ ] 반응형 표준 컨테이너/그리드 유틸 정리(문서화 or 헬퍼)
- [ ] 하드코딩 hex 색 사용처 grep 조사 → 토큰 치환 대상 목록화

## 1. 공통 셸 (Phase 1 — Phase 0 후, 페이지 작업의 전제)

파일: `components/AppLayout.tsx` · `Sidebar.tsx` · `Center.tsx` · `ProjectPanel.tsx` · `CompanyPanel.tsx` · `AdminPanel.tsx`

- [ ] `AppLayout` — 데스크톱 3영역 유지, 토큰화. 모바일 드로어 UX 정제(백드롭·전환·포커스 트랩)
- [ ] `Sidebar` — 모바일 내부 콘텐츠 터치/스크롤 친화(현 `w-56` 고정 내용 재구성), 활성 상태 표시 개선
- [ ] `Center`(우측 채팅/알림 센터) — 모바일에서 시트/드로어로 전환(현재 데스크톱 전용 폭)
- [ ] 좌측 패널들 — 모바일 노출 방식 결정(현재 `max-md:hidden`으로 숨김만)
- [ ] 라우트 전환 시 드로어 자동 닫힘 유지

## 2. 페이지 그룹별 (Phase 2 — Phase 1 후, 그룹 간 병렬 가능)

우선순위: **P1 = 발표 데모 핵심 동선 · 방문 잦음 / P2 = 기능 완결 / P3 = 관리자·부가**.

### 그룹 A — 대시보드 & 홈 (P1)
- [ ] `dashboard/page.tsx` — `grid-cols-3`/`grid-cols-2` → 반응형 그리드. 테이블 하드코딩 폭 제거. 챗봇 `h-64` 고정 → 반응형 높이. KpiCard 토큰화
- [ ] `/` 홈, `sign-in` — 로그인/랜딩 반응형·토큰 적용

### 그룹 B — 시뮬레이션 (P1)
- [ ] `simulation/page.tsx` — 3모드 탭·입력 폼 모바일 레이아웃
- [ ] `simulation/[id]/page.tsx` — 결과/비교/심층 뷰, 차트·`SimulationReportView` 반응형 (⚠️ 병합 시 sim-* 워크트리 변경 반영 확인)
- [ ] `simulations/page.tsx` — 이력 목록 카드/테이블 반응형

### 그룹 C — 매니지먼트 (P1~P2)
- [ ] `manage/page.tsx` — 이미 `grid-cols-1 md:grid-cols-4`(표준). 토큰화·미세 정리만
- [ ] `manage/campaigns/page.tsx` + `CampaignTable.tsx` — 8~13열 테이블 **모바일 카드뷰 전환**. 상단 컨트롤 `flex-wrap`
- [ ] `manage/campaigns/new` — 캠페인 생성 폼 반응형
- [ ] `manage/compare/page.tsx` — `grid-cols-4` → `grid-cols-1 md:grid-cols-2 lg:grid-cols-4`
- [ ] `manage/budget/page.tsx` — 예산 차트/그래프 반응형
- [ ] `manage/monitoring` · `manage/anomaly` · `manage/connect` — 각 반응형·토큰

### 그룹 D — 생성 & 채팅 (P2)
- [ ] `generator/page.tsx` · `generations/[id]/page.tsx` — 생성 폼·결과 시안 반응형
- [ ] `chat/[pid]`(+`/[sid]`) — 채팅 화면 모바일. 위젯(DebateStreamWidget 등) 반응형 (⚠️ chat-loop-earlystop 병합 반영 확인)

### 그룹 E — 프로젝트·계정·결제 (P2)
- [ ] `projects/page.tsx` · `projects/[id]/page.tsx`
- [ ] `profile` · `my-org` · `payment`(+success/fail) · `trash`

### 그룹 F — 관리자·기업 (P3)
- [ ] `admin/*` (dashboard/companies/manage-user/generations/chats/chat-log/check/inquiry)
- [ ] `company/*` (teams/projects/members/generations/chats)

### 그룹 G — 정적 (P3)
- [ ] `privacy` · `terms` · `data-deletion` — 토큰·타이포만 정리(반응형 단순)

## 3. 페이지 공통 개편 체크(각 페이지마다)

- [ ] 하드코딩 hex/px → 토큰·반응형 유틸 치환
- [ ] `grid-cols-N` 고정 → mobile-first 반응형 그리드
- [ ] 컨테이너 `max-w-screen-xl px-4 sm:px-6 lg:px-8` 표준 적용
- [ ] 테이블 모바일 전략(카드뷰/핵심열/가로스크롤) 적용
- [ ] 라이트/다크 양쪽 확인
- [ ] 터치 타깃 44px, 폼 label 연결
- [ ] Claude Preview로 모바일(375)·태블릿(768)·데스크톱(1280) 검증 스크린샷

## 4. 병합 후 워크트리 재분할안 (충돌 없이 병렬)

- **wt: fe-foundation** — Phase 0(토큰·tailwind·훅·shadcn) + Phase 1(공통 셸). **먼저 완료·병합**(전 페이지 전제).
- 이후 baseline 위에서 그룹별 병렬:
  - **wt: fe-dashboard** — 그룹 A
  - **wt: fe-simulation** — 그룹 B
  - **wt: fe-manage** — 그룹 C
  - **wt: fe-gen-chat** — 그룹 D
  - **wt: fe-account** — 그룹 E
  - **wt: fe-admin** — 그룹 F + G
- 그룹들은 서로 다른 페이지 디렉터리라 충돌 적음. 공통 컴포넌트(`ui/*`) 수정은 fe-foundation에서만, 이후엔 append 위주.

## 5. 착수 전 확정 필요 (도연님)

- [x] shadcn/ui 도입 여부 → **도입 확정** (2026-07-07)
- [x] 브랜드 톤 → **Toss 계열 유지·정제 확정** (리브랜딩 안 함, 2026-07-07)
- [ ] 컬러 토큰 네이밍 별칭(`fg`/`primary`) 및 채널 전환 여부 (착수 시)
- [ ] 차트 라이브러리 표준 1종 (병합 후 현행 확인하고)
