# 센터 구현 체크리스트 (루프 진행 상태)

> 매 루프 반복마다 이 파일을 갱신한다. `[x]` = 완료(검증까지). 정본 스펙 = `center-spec.md`.

## Phase 1 — 백엔드 토대
- [x] 제안 알림 신규 테이블(center_suggestions) 모델 + 마이그레이션 `0009_center_suggestions` (체인 단일 선형 재정렬 완료. 공유 DB엔 `uv run alembic upgrade head`로 0009 적용 필요)
- [ ] 제안 알림 자동생성 — 시뮬 완료 직후 "제너레이터 제안" 인라인 훅
- [ ] 제안 알림 자동생성 — 제너 완료 직후 "시뮬레이션 제안" 인라인 훅
- [ ] 집행 제안 훅 자리(판정 기준은 open-decisions §1 확정 전까지 TODO 스텁)
- [ ] 알림 병합 조회 API (management 이상감지 + 신규 제안)
- [ ] 통합 세션 목록 API (프로젝트 전체, org 스코프)
- [ ] 시안 3개 미리보기 데이터 조회 경로 확인/보강

## Phase 2 — 센터 shell
- [ ] 우측 접이식 aside (fixed, height 100%, 패널 폭, flex column)
- [ ] 접힘: 채팅·알림 버튼 세로 스택 + 미읽음 배지
- [ ] 펼침: 상단 두 버튼 탭 전환
- [ ] localStorage 상태 기억(펼침/접힘·마지막 센터)
- [ ] AppLayout에서 FloatingChat·NotificationBell·우하단 알림버튼 제거·센터로 교체

## Phase 3 — 필터 바
- [ ] 세그먼트 [안읽음·읽음·전체] (채팅/알림 각각)
- [ ] 프로젝트 드롭다운(기본 전체 프로젝트), space-between
- [ ] ADMIN 기업 드롭다운(프로젝트 왼쪽)

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
