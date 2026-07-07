# 센터 구현 체크리스트 (루프 진행 상태)

> 매 루프 반복마다 이 파일을 갱신한다. `[x]` = 완료(검증까지). 정본 스펙 = `center-spec.md`.

## Phase 1 — 백엔드 토대
- [x] 제안 알림 신규 테이블(center_suggestions) 모델 + 마이그레이션 `0008_center_suggestions` (체인 해결됨. 공유 DB엔 `uv run alembic upgrade head`로 0008 적용 필요)
- [x] 제안 알림 자동생성 — 시뮬 완료 직후 "제너레이터 제안" 인라인 훅 (core/center_suggestions.py 공용 헬퍼 + simulation_service `_record_gen_suggestion`)
- [x] 제안 알림 자동생성 — 제너 완료 직후 "시뮬레이션 제안" 인라인 훅 (generator_service `_record_sim_suggestion`, 시안 3개 미리보기 payload)
- [x] 집행 제안 훅 자리(판정 기준은 open-decisions §1 확정 전까지 TODO 스텁) (simulation_service `_record_gen_suggestion` 하단 TODO)
- [x] 알림 병합 조회 API (management 이상감지 + 신규 제안) — `GET /api/center/notifications`(org 스코프·COMPANY 제안숨김·정렬병합) + `POST /api/center/suggestions/{id}/read|dismiss` (api/routers/center.py)
- [x] 통합 세션 목록 API (프로젝트 전체, org 스코프) — `GET /api/center/sessions`(history.list_sessions_for_org, Project 조인 org 스코프·project_name)
- [x] 시안 3개 미리보기 데이터 조회 경로 확인/보강 — sim_suggest payload.candidates에 idx·copy·image_url 임베드, 폴백은 `GET /api/generator/generations/{source_gen_id}`

## Phase 2 — 센터 shell
- [x] 우측 접이식 aside (fixed, height 100%, 패널 폭 w-72, flex column) — components/center/Center.tsx
- [x] 접힘: 채팅·알림 버튼 세로 스택 + 미읽음 배지 (우측 가장자리 띠, 카운트 30s 폴링)
- [x] 펼침: 상단 두 버튼 탭 전환 (TabButton, 접기 버튼)
- [x] localStorage 상태 기억(펼침/접힘·마지막 센터) — center:expanded·center:tab
- [~] AppLayout에서 FloatingChat·NotificationBell·우하단 알림버튼 제거·센터로 교체 — `<Center/>` 마운트 완료. **제거는 대체 콘텐츠(Phase 4 알림·Phase 5 채팅) 동작 후로 유보**(회귀 방지). 지금은 공존.
- [x] api 클라이언트 center 블록(notifications·sessions·read·dismiss) + 타입(CenterNotificationItem·CenterSessionRow)

## Phase 3 — 필터 바
- [x] 세그먼트 [안읽음·읽음·전체] (채팅/알림 각각) — CenterFilterBar, Center가 chatSeg·alarmSeg 분리 보유
- [x] 프로젝트 드롭다운(기본 전체 프로젝트), space-between — Select, 기본값 '' = 전체 프로젝트
- [x] ADMIN 기업 드롭다운(프로젝트 왼쪽) — isAdmin일 때 상단에 기업 Select, 선택 시 setAdminOrgId(X-Org-Id)

## Phase 4 — 알림 센터
- [x] 병합 목록 렌더 — AlarmCenter, api.center.notifications + 세그먼트 read_at 필터
- [x] 아코디언: 접힘 제목만 · 단일 오픈 · 열 때 읽음 (management read / center readSuggestion)
- [x] 상세: 시뮬 제안→시안 3개(payload.candidates) / 제너 제안→시뮬 요약(resultSummary('sim', source_sim_id) 재사용)
- [x] 알림별 액션 버튼 → 프리필 이동 (시뮬 돌리기→/simulation, 생성해 보기→/generator, 상담하기→consult+채팅; selectProject로 컨텍스트 프리필)
- [x] 기존 지금 점검·상담·무시 이관 (notifyScan·consult·resolve/dismissSuggestion, useNotificationStream SSE 구독)

## Phase 5 — 채팅 센터
- [x] 세션 목록(height 100%) 이식 — ChatCenter, api.center.sessions(검색·새채팅·삭제·미확인 배지·전환 이관)
- [x] 세션 클릭 → 50/50 + 하단 라이브 채팅(기존 ChatConversation 재사용) — ADMIN Preview 검증(입력창·SimResultWidget·이력 렌더)
- [x] 전체 프로젝트 통합 세션 표시 — projectId '' → org 전체(project_name 표시), 검증(16세션)
- [x] 전체 프로젝트 상태에서 입력 시 프로젝트 강제 선택 — 새 채팅 시 needProject 안내
- [x] 패널 채팅(ProjectChatSection)·FloatingChat 완전 제거(기능 누락 0) — FloatingChat·ProjectChatSection 파일 삭제, AppLayout NotificationBell 렌더 제거, layout.tsx FloatingChat 제거, AdminPanel·ProjectPanel ProjectChatSection 제거(showChat prop 정리). 상담하기는 AlarmCenter→onOpenChat으로 센터 채팅 탭 전환. Preview 검증(플로팅·벨 부재·센터 정상·콘솔 에러 0)
- [x] (fix) ADMIN 기업 전환 시 목록 미갱신 버그 — orgKey prop으로 AlarmCenter·ChatCenter 재조회 트리거

## Phase 6 — 권한 분기
- [ ] ADMIN: 기업 미선택 시 두 센터 disable + 안내
- [ ] COMPANY: 읽기전용 채팅(입력 불가·읽음표시 X), management 알림만, /chat 차단 완화
- [ ] USER: 기업 드롭다운 없음, 전 기능 사용

## Phase 7 — 검증·문서
- [x] ruff(백엔드) 통과 (Phase 1 커밋들)
- [x] gen_docs 재생성(라우터/페이지 변경분) (center 엔드포인트 4개 반영)
- [~] Claude Preview로 역할별 동작 검증(증거 캡처) — **ADMIN 라이브 검증 완료**(2026-07-06): shell 접힘/펼침·필터바·알림 센터 렌더, /api/center/notifications·sessions 200, org 스코프(X-Org-Id) 동작(미선택 org_selected=false, 선택 시 true·세션16). 콘솔 에러 0. preview_screenshot은 이 페이지에서 타임아웃 → preview_eval DOM 확인으로 대체. **COMPANY/USER는 Cognito에 계정 없어(admin만 잔존) 계정 발급 후 검증 필요.**
- [x] 기능 단위 커밋 (phase별 커밋 진행 중)
