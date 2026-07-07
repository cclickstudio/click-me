# 센터(Center) — 통합 채팅·알림 사이드 스펙

> 우하단 플로팅 채팅 · 우하단 알림 버튼 · 우상단 알림 벨을 **오른쪽 접이식 aside "센터"** 하나로 통합한다.
> 이 문서가 구현의 단일 정본(source of truth). 사용자 확답(2026-07-06) 기반. 미결정 항목은 §9.

## 1. 용어

- **센터(Center)** — 화면 오른쪽에 붙는, 펼쳤다 접었다 하는 세로 aside. `flex-direction: column`.
- **패널(Panel)** — 왼쪽에 뜨는 `AdminPanel` / `CompanyPanel` / `ProjectPanel`. (기존 유지, 단 채팅 기능은 제거 — §6.)
- **채팅 센터 / 알림 센터** — 센터를 채팅 버튼으로 열면 채팅 센터, 알림 버튼으로 열면 알림 센터.

## 2. 통합 범위 (무엇을 없애는가)

기존 셋을 **전부 제거하고 센터로 일원화**한다.

- 우하단 플로팅 채팅 `frontend/src/components/chat/FloatingChat.tsx` — 제거.
- 우상단 알림 벨 `frontend/src/components/manage/notifications/NotificationBell.tsx` (+ `NotificationPanel.tsx`) — 센터로 이관/대체.
- 우하단 알림 버튼 — 제거.
- `AppLayout.tsx`에서 `<NotificationBell />` 등 렌더 지점을 센터로 교체.

## 3. 레이아웃

- 위치 — 화면 오른쪽 고정(`fixed`). 본문을 밀지 않고 **위에 떠서 덮는다**.
- 펼침 크기 — **`height: 100%`, 세로로 긴 바.** 폭은 **왼쪽 패널과 동일 규격**(패널 펼침 폭 `w-72` = 288px 기준에 맞춘다).
- 접힘 상태 — 오른쪽 가장자리에 **채팅 버튼 + 알림 버튼이 세로로 스택**된 얇은 띠만 보인다(살짝 보이는 형태). 두 버튼에 **미읽음 카운트 배지** 표시.
- 펼친 뒤 채팅↔알림 전환 — 접힘 때 쓰던 **두 버튼을 상단 탭처럼** 남겨 눌러 전환.
- 상태 기억 — 펼침/접힘 + 마지막으로 연 센터(채팅/알림)를 `localStorage`에 저장·복원.
- 모든 구성은 `flex-direction: column`.

## 4. 최상단 필터 바 (채팅/알림 **각각** 보유)

`space-between`으로 좌우 배치.

- 왼쪽 — 세그먼트 `[안읽음 · 읽음 · 전체]`.
  - 알림 — 알림 read 상태 기준 필터.
  - 채팅 — 세션 `unread_count` 기준 필터.
- 오른쪽 — 프로젝트 선택 드롭다운. **기본값 = 전체 프로젝트.**
- ADMIN 한정 — 프로젝트 드롭다운 **왼쪽에 기업 선택 드롭다운** 추가(§7).

## 5. 알림 센터

### 5.1 데이터 소스 (병합)

한 목록에 **기존 management 이상감지 알림 + 신규 제안 알림을 병합**해 보여준다. `payload.kind`(또는 타입 필드)로 종류 구분.

### 5.2 신규 제안 알림 — 자동 생성 (신규 백엔드)

잡 완료 **직후 인라인**으로 생성(스케줄러 주기 점검 아님). 저장은 **신규 테이블**(§8).

| 트리거(발생 이유) | 알림 종류(제목) | 아코디언 상세 | 액션 버튼 |
|---|---|---|---|
| 제너레이터를 돌림 | **시뮬레이션 제안** | 제너레이터가 만든 **광고 시안 3개 미리보기** | 시뮬레이션 돌리기 |
| 시뮬레이션을 돌려 개선안을 받음 | **제너레이터 제안** | `GET /api/chat/result-summary?kind=sim` 재사용 → **시뮬 결과 요약 + 개선안** | 생성해 보기 |
| 시뮬 결과가 좋음 | **집행 제안** ("결과가 아주 좋아요, 집행하시겠어요?") | 결과 요약 | (집행 관련 — §9 결과 판정 기준 확정 후) |
| management 이상감지(노출0 등) | 기존 이상감지 알림 | 기존 상세 | 상담하기 등 |

> "발생 이유" 관계: 시뮬레이션 제안 ← 제너레이터 실행 / 제너레이터 제안 ← 시뮬레이션 실행(개선안).

### 5.3 아코디언 UX

- 접힌 알림은 **제목만**(예: `시뮬레이션 제안`) 간결하게.
- **한 번에 하나만 열림** — 다른 걸 열면 기존 열린 건 자동으로 접힘.
- **아코디언을 열 때 읽음 처리**(진입 일괄 읽음 아님).
- 상세 아래에 **알림별 맞춤 액션 버튼**. 클릭 시 **해당 페이지로 프리필 이동**(시뮬레이션 돌리기→/simulation, 생성해 보기→/generator, 상담하기→상담 채팅).
- 기존 "지금 점검" 스캔·[상담하기]/[무시] 액션은 알림 센터로 이관.

## 6. 채팅 센터

- 첫 화면 — `height: 100%`로 **채팅 내역 = 세션 목록**(기존 `ProjectChatSection`을 이식, 특정 대화 로그가 아님).
- 세션 클릭 — 내역을 `height: 50%`로 줄이고, **하단 50%에 라이브 채팅**(기존 `FloatingChat` 대화 UI — 입력창·SSE·위젯 그대로 재사용).
- 전체 프로젝트 세션 — 필터가 "전체 프로젝트"면 **프로젝트 전체 세션을 통합 표시**. → **신규 통합 API** 필요(현재 세션 목록 API는 프로젝트 단위).
- 라이브 채팅 시작 시 프로젝트가 "전체 프로젝트"면 **프로젝트를 직접 선택**하게 유도(전체 상태로는 입력 불가).

### 6.1 패널 채팅 완전 제거

- `AdminPanel.tsx` / `ProjectPanel.tsx`(및 채팅 있는 패널)에서 `ProjectChatSection` **완전 제거**.
- 기존 패널 채팅의 모든 기능(세션 목록·검색·새 채팅·삭제·미확인 배지·활성세션 전환)을 **하나도 빠짐없이 채팅 센터로 이관**.
- `FloatingChat` 컴포넌트도 제거(센터가 대체).

## 7. 권한별 구성

| 역할 | 기업 드롭다운 | 프로젝트 드롭다운 | 채팅 | 알림 | 비고 |
|---|---|---|---|---|---|
| **ADMIN** | 있음 | 있음(선택 기업 소속으로 한정) | 사용 | 사용 | 기업 미선택 시 두 센터 모두 **disable**, "기업을 선택해주세요" 안내. 선택 기업을 org 스코프(`X-Org-Id`)로 로드. |
| **COMPANY** | 없음 | 있음 | **읽기전용**(입력 불가, 읽음표시 안 함) | **management 알림만**(시뮬·제너 제안 숨김) | 현재 `AppLayout`의 `/chat` 완전 차단을 **읽기전용 허용으로 완화**. 매니지먼트 외 기능 불가. |
| **USER** | **없음**(기업 고정) | 있음 | 사용(입력 가능) | 사용(모든 제안 알림) | ADMIN 구성과 동일, 기업 드롭다운만 제거. |

## 8. 데이터 모델

- 제안 알림 — **신규 테이블** 신설(Alembic). 최소 컬럼(안): `id`, `type`(sim_suggest·gen_suggest·launch_suggest…), `reason`(발생 이유/트리거), `project_id`, `org_id`, `source_sim_id`/`source_gen_id`, `payload`(시안 미리보기·요약 등), `read_at`, `created_at`, `dedup_key`.
- 기존 management 이상감지 알림(`ManagementNotification`)·`automation_runs`는 그대로 두고, 알림 센터가 **양쪽을 병합 조회**.
- 통합 세션 목록 — 신규 API(프로젝트 전체 세션, org 스코프).

## 9. 미결정 / 후속 (메모)

- **[결과 "좋음" 판정 기준]** — "결과가 아주 좋아요→집행 제안"의 KPI·임계값은 **시뮬 팀원과 상의 후 확정**. → `docs/center/open-decisions.md`.
- **[모바일 반응형]** — 센터의 모바일 동작은 **반응형 작업 시 별도 검토**(현재는 데스크톱 기준). → `docs/center/open-decisions.md`.

## 10. 관련 코드 포인터

- 레이아웃 shell — `frontend/src/components/AppLayout.tsx`
- 패널 — `AdminPanel.tsx` · `CompanyPanel.tsx` · `ProjectPanel.tsx`
- 채팅 — `chat/FloatingChat.tsx` · `chat/ChatController.tsx` · `chat/ProjectChatSection.tsx` · `chat/ChatConversation.tsx`
- 알림 — `manage/notifications/NotificationBell.tsx` · `NotificationPanel.tsx` · `useNotificationStream.ts`
- 시뮬 요약 API — `backend/api/routers/chat.py` `GET /api/chat/result-summary` (`kind=sim`)
- 크로스도메인 자동화 적재 — `backend/core/automation.py` (`record_automation_run` / 레지스트리)
- 상태 — `ProjectContext`(useProjects) · `ChatController` · `AuthProvider`
