# Task 14: 전체 검증 + 문서 마감

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md` §7·§8
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 프론트는 `cd frontend` · 커밋은 명시 파일만 add.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션.
> 선행: Task 0~13 전부.

---

**Files:**
- Modify: `docs/management/remediation-알림-채널-조율.md` (§6 결정 체크)
- Modify: `docs/management/remediation-advisor-검증-가이드.md` (채널 이행 노트)

- [ ] **Step 1: 백엔드 전체 회귀**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd backend && uv run pytest -q
```
Expected: 전부 PASS (기존 chat_sink·notify_scan·context 테스트 포함 무회귀)

- [ ] **Step 2: 프론트 검증**

```bash
cd frontend && pnpm lint && pnpm build
```

- [ ] **Step 3: 문서 마감**

- `docs/management/remediation-알림-채널-조율.md` §6 체크박스 갱신: 채널 방향 **C 확정** · 세션 정책(프로젝트당 전용 세션 재사용) · [무시] 재통지(완전 억제 — `resolution='ignored'`만) · 옵션 선택 UX(버튼 + [기타]) 확정 표기.
- `docs/management/remediation-advisor-검증-가이드.md`에 이행 노트 추가: "`MANAGEMENT_CHAT_NOTIFY_ENABLED=true` → `MANAGEMENT_NOTIFY_CHANNEL=chat`(또는 `panel`)". 데모 절차의 스위치 명을 새 설정으로 교체.

- [ ] **Step 4: 수동 E2E (mock, 로컬)**

```bash
# 터미널 1
cd backend && uv run uvicorn api.main:app --reload --port 8000
# 터미널 2
cd frontend && pnpm dev
```

`backend/.env`에 `MANAGEMENT_NOTIFY_CHANNEL=panel` 설정 후:

① 로그인 → 수동 스캔 트리거(`POST /api/management/anomaly/notify-scan` — curl 또는 기존 UI 버튼)
② 상단 벨 배지 점등(SSE 실시간) 확인
③ 패널 열기 → 카드(캠페인명·이상 유형·프로젝트 라벨) 확인 + 열람 시 배지 소거(bulk read)
④ [상담하기] → 채팅 열림 · 상담 메시지 · 옵션 버튼(3~4개 + [기타]) 렌더 확인
⑤ 옵션 버튼 클릭 → 정규화 메시지 전송 → 도구(tool_hint) 진행 확인 / [기타] → 입력창 포커스 확인
⑥ 다른 카드 [무시] → 재스캔 시 같은 (캠페인, 이상) 재통지 없음 확인
⑦ (선택) 이상 해소된 mock 상태로 재스캔 → 알림 auto_normal 자동 해소 확인

사용자에게 Claude Preview 실화면 검증을 제안한다(CLAUDE.md 규칙 ⑤): *"실제 화면도 Claude Preview로 띄워서 동작을 보여드릴까요?"*

- [ ] **Step 5: 최종 커밋**

```bash
git add docs/management
git commit -m "edit: 알림 채널 C안 결정 반영 — 조율 문서 §6 체크·검증 가이드 이행 노트"
```
