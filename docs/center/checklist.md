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
- [ ] 병합 목록 렌더
- [ ] 아코디언: 접힘 제목만 · 단일 오픈 · 열 때 읽음
- [ ] 상세: 시뮬 제안→시안 3개 / 제너 제안→요약+개선안(result-summary 재사용)
- [ ] 알림별 액션 버튼 → 프리필 이동
- [ ] 기존 지금 점검·상담·무시 이관

## Phase 5 — 채팅 센터
- [ ] 세션 목록(height 100%) 이식
- [ ] 세션 클릭 → 50/50 + 하단 라이브 채팅(기존 대화 UI 재사용)
- [ ] 전체 프로젝트 통합 세션 표시
- [ ] 전체 프로젝트 상태에서 입력 시 프로젝트 강제 선택
- [ ] 패널 채팅(ProjectChatSection)·FloatingChat 완전 제거(기능 누락 0)

## Phase 6 — 권한 분기
- [ ] ADMIN: 기업 미선택 시 두 센터 disable + 안내
- [ ] COMPANY: 읽기전용 채팅(입력 불가·읽음표시 X), management 알림만, /chat 차단 완화
- [ ] USER: 기업 드롭다운 없음, 전 기능 사용

## Phase 7 — 검증·문서
- [ ] ruff(백엔드) 통과
- [ ] gen_docs 재생성(라우터/페이지 변경분)
- [ ] Claude Preview로 역할별 동작 검증(증거 캡처)
- [ ] 기능 단위 커밋
