# Task 0: 준비 — dev 머지 + 팀 공지

> 상위 계획(인덱스): `docs/superpowers/plans/2026-07-03-remediation-hybrid-notification.md` · 스펙: `docs/superpowers/specs/2026-07-03-remediation-hybrid-notification-design.md`
> **실행 규칙**: 백엔드 명령은 `cd backend` 후 실행 · 커밋 전 `uv run ruff format . && uv run ruff check . --fix`(커밋은 명시 파일만 add) · 타임스탬프 UTC-aware(naive 금지) · 새 파일 첫 줄 한국어 헤더 주석 · 🅰 소유 파일(detection/, approval.py, agents/diagnosis*) 수정 금지.
> **시그니처 정본**: 인덱스의 "계약 스냅샷" 섹션 — 이 문서와 어긋나면 스냅샷을 따르고 차이를 보고할 것.

---

**Files:** 없음 (git 작업만)

- [ ] **Step 1: dev 머지로 0004 마이그레이션 확보**

```bash
git fetch origin dev && git merge origin/dev
ls backend/alembic/versions/   # 0004_generator_kb_search_vector.py 있어야 함
```

충돌 시 자기 도메인 파일(`domain/management/`·자기 라우터)은 우리 쪽, 공통부(`core/`·`api/main.py`)는 dev 쪽 우선으로 해소 후 사용자에게 보고.

- [ ] **Step 2: 팀 공지 확인(사용자에게 위임)**

사용자에게 다음 공지가 팀에 전달됐는지 확인 요청(구현은 진행 가능, 머지 전 공지 필수):
① `core/models.py`+Alembic 0005 신설 ② `AppLayout.tsx` 벨 추가 ③ `core/schemas.py` ChatRequest 필드 1개 추가 ④ `MANAGEMENT_CHAT_NOTIFY_ENABLED` → `MANAGEMENT_NOTIFY_CHANNEL` 이행.
