# admin management org 스코프 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** admin이 management를 다른 기능과 동일하게 볼 수 있게 한다 — operational은 org 선택(impersonate), DB 리스트는 전 org 조회.

**Architecture:** `X-Org-Id` 헤더를 라우터 레벨 yield 의존성이 ContextVar에 캡처 → org 해석기(`_require_org_id`/`_require_org_id_write`/`_scope_org_or_all`)가 role 분기로 스코프를 정한다. 헤더는 ADMIN일 때만 참조(비-ADMIN은 무시). 공통부(`api/main.py`) 무변경, 전부 `management.py` 안에서 처리.

**Tech Stack:** FastAPI, SQLAlchemy(async), pytest(+asyncio), FastAPI TestClient. 프론트: Next.js/TS, `frontend/src/lib/api.ts`.

**Spec:** `docs/superpowers/specs/2026-07-01-admin-management-org-scope-design.md`

**리뷰 반영(수정 이력)**
- kpi-overrides는 **impersonate-only**(all-org는 campaign_id 충돌·shape 파손으로 제외, YAGNI).
- **organization_name 표시는 이번 범위 제외**(공유 org-list context 신설 회피). 백엔드는 org_id/tenant_id만 반환, 화면도 id 기준. name은 후속.
- 감사 wiring은 fragile한 HTTP 통합 대신 **`_require_org_id_write` seam**(org 해석+emit 원자화). 감사는 **시도 시점 기록**(`outcome="attempted"`) — 접근 사실 감사, 성공/실패 3단계는 안 함.
- write 치환 누락은 **매트릭스 체크박스 + Task 6 정적 대조**로 방지.
- access log wiring도 **테스트로 고정**(monkeypatch sink).
- 리스트 테스트는 stmt 캡처 → `whereclause` 유무. **limit clamp는 `_clamp_limit_offset` 단위 테스트**.
- ContextVar 테스트는 **로컬 APIRouter(명시 import) + autouse reset fixture**.

**주의(공통 규칙)**
- 백엔드 `.py` 수정 후 커밋 전 `cd backend && uv run ruff format . && uv run ruff check . --fix`.
- 테스트 실행: `cd backend && uv run pytest ../test/backend/management/<file> -v` (`pyproject.toml`의 `testpaths=["../test/backend"]`).
- 커밋 컨벤션: `add|edit|fix: 한국어 설명`.

---

## 파일 구조

- Modify: `backend/api/routers/management.py` — ContextVar·의존성·해석기·검증·스코프·clamp·access log·감사·엔드포인트.
- Modify: `frontend/src/lib/api.ts` — `request()` management 한정 `X-Org-Id` + `adminOrgId` 유틸.
- Modify: `frontend/src/components/AuthProvider.tsx` — 비-ADMIN 시 `adminOrgId` clear.
- Create: `frontend/src/components/manage/AdminOrgPicker.tsx` — admin org 선택 드롭다운.
- Create: `docs/superpowers/plans/2026-07-01-admin-management-org-matrix.md` — Task 1 산출물.
- Test: `test/backend/management/test_admin_org_scope.py` — 신규 테스트 집약.

---

## Task 1: (Phase 0) 엔드포인트 매트릭스 작성

**Files:**
- Create: `docs/superpowers/plans/2026-07-01-admin-management-org-matrix.md`

- [ ] **Step 1: org 해석 호출부 수집**

Run: `cd backend && grep -nE '_require_org_id|_resolve_org_id|user_org_id|OrganizationMember.*user_id == user\.id|require_user_org' api/routers/management.py`
각 호출부의 enclosing 엔드포인트(직전 `@router.*`)를 확인한다.

- [ ] **Step 2: 세 부류로 분류표 + write 체크박스 작성**

문서에 표 작성. 열: `{엔드포인트, 라인, 부류(a/b/c), 처리, write여부, 치환완료(체크박스)}`.
- (a) 순수 org-scope → `_require_org_id`(operational read) / `_require_org_id_write`(operational write) / `_scope_org_or_all`(리스트).
- (b) user 신원 병행(`approve(..., str(user.id))` 2637/2760/2941, `updated_by=user.id` 1633) → 로직 불변.
- (c) 멤버십 직접 해석(`meta_connect` 3255) → admin 대리 불가(현행 유지, 409).
Phase 2 대상: `/created-campaigns`(497, all-org). `/kpi-overrides`(1581) impersonate-only. `/compare*`·`/budget`은 live Meta reader 사용 여부 확인 후 impersonate-only 태그.
**`write=Y & operational` 행마다 `- [ ]` 체크박스**를 둔다 — Task 6에서 `_require_org_id` → `_require_org_id_write` 치환 후 체크(누락 방지 체크리스트).

- [ ] **Step 3: 커밋**

```bash
git add docs/superpowers/plans/2026-07-01-admin-management-org-matrix.md
git commit -m "add: management org 해석 엔드포인트 매트릭스 (Phase 0)"
```

---

## Task 2: (Phase 1) ContextVar + 헤더 캡처 의존성

**Files:**
- Modify: `backend/api/routers/management.py` (현재 135번 줄 `router = APIRouter()`)
- Test: `test/backend/management/test_admin_org_scope.py`

- [ ] **Step 1: 실패 테스트 작성** (신규 파일)

```python
# admin org 스코프 — 헤더 캡처·해석기·검증·전역뷰 테스트
import uuid
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db


@pytest.fixture(autouse=True)
def _reset_org_ctx():
    """각 테스트 전후로 ContextVar 초기화 — 요청 밖 누수/순서 의존 제거."""
    token = management._selected_org_ctx.set(None)
    yield
    management._selected_org_ctx.reset(token)


def test_header_captured_during_and_reset_after():
    """캡처 의존성이 요청 중 헤더를 ContextVar에 넣고 요청 후 reset 하는지 (로컬 router로 전역 오염 없이)."""
    seen = {}
    probe = APIRouter(dependencies=[Depends(management._capture_selected_org)])

    @probe.get("/__ctxprobe")
    async def _p():
        seen["during"] = management._selected_org_ctx.get()
        return {"ok": True}

    app = FastAPI()
    app.include_router(probe)
    TestClient(app).get("/__ctxprobe", headers={"X-Org-Id": "org-abc"})
    assert seen["during"] == "org-abc"
    assert management._selected_org_ctx.get() is None  # 요청 후 reset
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py::test_header_captured_during_and_reset_after -v`
Expected: FAIL — `management._selected_org_ctx`/`_capture_selected_org` 없음.

- [ ] **Step 3: 구현**

`management.py` 상단 import에 `from contextvars import ContextVar` 추가, 기존 `from fastapi import ...`에 `Header` 병합. router 정의부 교체:

```python
_selected_org_ctx: ContextVar[str | None] = ContextVar("selected_org", default=None)


async def _capture_selected_org(x_org_id: str | None = Header(None, alias="X-Org-Id")):
    """요청당 1회 X-Org-Id를 ContextVar에 캡처, 종료 시 reset (누수 방지)."""
    token = _selected_org_ctx.set(x_org_id)
    try:
        yield
    finally:
        _selected_org_ctx.reset(token)


router = APIRouter(dependencies=[Depends(_capture_selected_org)])
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py::test_header_captured_during_and_reset_after -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "add: management X-Org-Id 헤더 캡처 ContextVar 의존성"
```

---

## Task 3: (Phase 1) `_validated_org` 검증 헬퍼

**Files:**
- Modify: `backend/api/routers/management.py` (imports + `_require_org_id` 근처, 현재 2423번 줄)
- Test: `test/backend/management/test_admin_org_scope.py`

- [ ] **Step 1: 실패 테스트 작성** (append)

```python
class _OrgDB:
    """Organization.status 조회만 흉내내는 최소 FakeDB."""
    def __init__(self, status):
        self._status = status

    async def scalar(self, *_a, **_k):
        return self._status


@pytest.mark.asyncio
async def test_validated_org_bad_uuid_400():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB("ACTIVE"), "not-a-uuid", require_active=True)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_validated_org_missing_404():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB(None), str(uuid.uuid4()), require_active=True)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_validated_org_inactive_blocked_for_operational_409():
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB("SUSPENDED"), str(uuid.uuid4()), require_active=True)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_validated_org_inactive_allowed_for_read():
    org = uuid.uuid4()
    got = await management._validated_org(_OrgDB("SUSPENDED"), str(org), require_active=False)
    assert got == org
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k validated_org -v`
Expected: FAIL — `_validated_org` 없음.

- [ ] **Step 3: 구현**

`management.py`의 `from core.models import ...`에 `Organization` 병합. `_require_org_id` 정의 위에 추가:

```python
async def _validated_org(db, sel: str, *, require_active: bool) -> UUID:
    """X-Org-Id 검증. operational(require_active=True)은 ACTIVE만, read는 존재만."""
    try:
        org_uuid = UUID(sel)
    except ValueError as exc:
        raise HTTPException(400, "X-Org-Id 형식 오류") from exc
    status = await db.scalar(select(Organization.status).where(Organization.id == org_uuid))
    if status is None:
        raise HTTPException(404, "선택한 조직을 찾을 수 없습니다.")
    if require_active and str(status).upper() != "ACTIVE":
        raise HTTPException(409, "비활성 조직은 선택할 수 없습니다.")
    return org_uuid
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k validated_org -v`
Expected: PASS (4개)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "add: management _validated_org (operational=active, read=존재)"
```

---

## Task 4: (Phase 1) `_require_org_id` role 인지 해석기 교체

**Files:**
- Modify: `backend/api/routers/management.py` (현재 2423번 줄 `_require_org_id = require_user_org`)
- Test: `test/backend/management/test_admin_org_scope.py`

- [ ] **Step 1: 실패 테스트 작성** (append) — IDOR 회귀 포함

```python
class _MembershipDB:
    """require_user_org 경로 — 멤버십 org 반환."""
    def __init__(self, org):
        self._org = org

    async def scalar(self, *_a, **_k):
        return self._org


@pytest.mark.asyncio
async def test_non_admin_ignores_header_uses_own_org():
    """IDOR 회귀 — 비-ADMIN이 X-Org-Id 보내도 무시하고 자기 org."""
    own = uuid.uuid4()
    management._selected_org_ctx.set(str(uuid.uuid4()))  # 남의 org 힌트
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    assert await management._require_org_id(user, _MembershipDB(own)) == own


@pytest.mark.asyncio
async def test_admin_without_header_400():
    from fastapi import HTTPException
    user = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    with pytest.raises(HTTPException) as e:
        await management._require_org_id(user, _OrgDB("ACTIVE"))
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_admin_with_header_uses_selected_org():
    sel = uuid.uuid4()
    management._selected_org_ctx.set(str(sel))
    user = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    assert await management._require_org_id(user, _OrgDB("ACTIVE")) == sel
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k "non_admin_ignores or admin_without_header or admin_with_header" -v`
Expected: FAIL — 현재 별칭이라 role 분기 없음.

- [ ] **Step 3: 구현**

`_require_org_id = require_user_org  # ...` 한 줄을 교체:

```python
async def _require_org_id(user, db) -> UUID:
    """operational org 해석. ADMIN은 X-Org-Id로 impersonate, 비-ADMIN은 자기 org(미소속 409)."""
    if user.role.upper() == "ADMIN":
        sel = _selected_org_ctx.get()
        if not sel:
            raise HTTPException(400, "관리자는 조직을 선택하세요 (X-Org-Id 헤더).")
        return await _validated_org(db, sel, require_active=True)
    return await require_user_org(user, db)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -v`
회귀: `cd backend && uv run pytest ../test/backend/management/test_authz_hardening.py -v`
Expected: 신규 PASS + 기존 authz PASS(비-ADMIN 미소속 409 불변).

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "add: management _require_org_id role 인지(ADMIN impersonate) 해석기"
```

---

## Task 5: (Phase 1) `meta_connect` admin 대리 연결 차단 명문화

**Files:**
- Modify: `backend/api/routers/management.py:3240-3258` (`meta_connect`)
- Test: `test/backend/management/test_admin_org_scope.py`

- [ ] **Step 1: 핀 테스트 작성** (append)

```python
def _client(user, db):
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_admin_cannot_impersonate_meta_connect():
    """org 소유자 액션(Meta 연결)은 admin 대리 불가 → 409."""
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")

    class _DB:
        async def scalar(self, *_a, **_k):
            return None  # admin은 멤버십 없음

    res = _client(admin, _DB()).get(
        "/api/management/meta/connect", headers={"X-Org-Id": str(uuid.uuid4())}
    )
    assert res.status_code == 409
```

- [ ] **Step 2: 현행 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k meta_connect -v`
`meta_connect`는 이미 멤버십 None이면 409(3257)라 통과할 수 있다. 회귀 방지(pin)가 목적.

- [ ] **Step 3: 구현(명문화)**

`meta_connect`의 org 해석부(3254-3258)에 주석 추가(로직 불변):

```python
    # NOTE: org 소유자만 자기 Meta를 연결한다. admin impersonation(X-Org-Id) 대상이 아니며,
    # admin은 멤버십이 없어 아래 409로 자연 차단된다(설계: (c) 멤버십 직접 해석).
    org_id = await db.scalar(
        select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
    )
    if org_id is None:
        raise HTTPException(409, "소속 조직이 없습니다 — 조직 연결 후 시도하세요.")
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k meta_connect -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "add: meta_connect admin 대리 연결 차단 명문화 + 회귀 테스트"
```

---

## Task 6: (Phase 1) impersonation 감사 — `_require_org_id_write` seam

**Files:**
- Modify: `backend/api/routers/management.py` (감사 헬퍼 + write 엔드포인트 org 해석 치환)
- Test: `test/backend/management/test_admin_org_scope.py`

**설계:** emit을 별도 호출로 흩뿌리면 누락 위험이 크다. org 해석과 emit을 원자적으로 묶은 `_require_org_id_write`를 write 엔드포인트가 부르게 해서 **"org를 해석하는 write는 반드시 감사한다"를 구조적으로 보장**한다. 감사는 **시도 시점**(org 해석 직후) 기록이며 `outcome="attempted"`로 명시한다 — 목적은 "admin이 org의 토큰/컨텍스트에 접근했다"는 사실 감사(성공/실패 3단계 추적은 안 함).

- [ ] **Step 1: audit append API & write 대상 확인**

Run: `cd backend && grep -nE '_AUDIT_LOG|def record|def append|@router.(post|put|delete)' api/routers/management.py | head -40`
`_AUDIT_LOG`의 이벤트 추가 **메서드명(`record`/`append` 등)과 sync/async 여부**를 확인한다(아래는 `async record` 가정 — sync면 `await` 제거). Task 1 매트릭스의 `write=Y & operational` 행 = 치환 대상.

- [ ] **Step 2: 실패 테스트 작성** (append) — helper 단위(HTTP 없음)

```python
@pytest.mark.asyncio
async def test_emit_impersonation_audit_records(monkeypatch):
    captured = []

    class _Sink:
        async def record(self, **kw):  # Step 1의 실제 메서드명/시그니처로 맞춤
            captured.append(kw)

    monkeypatch.setattr(management, "_AUDIT_LOG", _Sink())
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    org = uuid.uuid4()
    await management._emit_impersonation_audit(admin, org, action="approve")
    assert captured and captured[0]["on_behalf_of_org"] == str(org)
    assert captured[0]["actor"] == str(admin.id)
    assert captured[0]["outcome"] == "attempted"


@pytest.mark.asyncio
async def test_emit_impersonation_audit_noop_for_non_admin(monkeypatch):
    captured = []

    class _Sink:
        async def record(self, **kw):
            captured.append(kw)

    monkeypatch.setattr(management, "_AUDIT_LOG", _Sink())
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    await management._emit_impersonation_audit(user, uuid.uuid4(), action="approve")
    assert captured == []


@pytest.mark.asyncio
async def test_require_org_id_write_resolves_and_emits(monkeypatch):
    """seam — org 해석 결과를 반환하고 emit을 원자적으로 호출한다(admin)."""
    calls = []

    async def _spy(user, org_id, *, action):
        calls.append((str(org_id), action))

    monkeypatch.setattr(management, "_emit_impersonation_audit", _spy)
    sel = uuid.uuid4()
    management._selected_org_ctx.set(str(sel))
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    got = await management._require_org_id_write(admin, _OrgDB("ACTIVE"), action="approve")
    assert got == sel
    assert calls == [(str(sel), "approve")]


@pytest.mark.asyncio
async def test_require_org_id_write_non_admin_returns_org(monkeypatch):
    """비-admin도 org는 반환. 실제 감사 미기록 보장은 emit 내부 noop 테스트가 담당."""
    async def _spy(*_a, **_k):
        return None

    monkeypatch.setattr(management, "_emit_impersonation_audit", _spy)
    own = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    got = await management._require_org_id_write(user, _MembershipDB(own), action="approve")
    assert got == own
```

- [ ] **Step 3: 구현**

```python
async def _emit_impersonation_audit(user, org_id, *, action: str) -> None:
    """admin이 org를 선택(impersonate)해 수행하려는 write/실행을 감사에 남긴다.
    org 해석 직후 호출되므로 '시도'(outcome=attempted)를 기록한다 — 토큰/컨텍스트 접근 사실이 감사 대상."""
    if user.role.upper() != "ADMIN":
        return
    await _AUDIT_LOG.record(
        category="impersonation",
        actor=str(user.id),
        on_behalf_of_org=str(org_id),
        action=action,
        outcome="attempted",
    )


async def _require_org_id_write(user, db, *, action: str) -> UUID:
    """operational WRITE용 org 해석 — org 확정 후 impersonation 감사를 원자적으로 남긴다."""
    org_id = await _require_org_id(user, db)
    await _emit_impersonation_audit(user, org_id, action=action)
    return org_id
```
Task 1 매트릭스 `write=Y & operational` 엔드포인트의 `org_id = await _require_org_id(user, db)`를 `org_id = await _require_org_id_write(user, db, action="<action명>")`으로 치환(action명: approve/execute/activate/pause/budget_commit/link_simulation 등).

- [ ] **Step 4: 통과 확인 + 치환 정적 대조**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k "impersonation_audit or require_org_id_write" -v`
**정적 대조:** Task 1 매트릭스의 `write=Y` 각 라인이 `_require_org_id_write`를 쓰는지 확인하고 매트릭스 체크박스를 채운다.
Run(참고): `cd backend && grep -nE '_require_org_id\(' api/routers/management.py` — 여기 매칭되는 라인 중 매트릭스 write=Y 엔드포인트가 남아 있으면 치환 누락.
회귀: `cd backend && uv run pytest ../test/backend/management -k "activation or approve or budget or link" -v`
Expected: PASS + 치환 누락 0.

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py docs/superpowers/plans/2026-07-01-admin-management-org-matrix.md
git commit -m "add: impersonation 감사 _require_org_id_write seam (org 해석+감사 원자화)"
```

---

## Task 7: (Phase 2) `_scope_org_or_all` + `_clamp_limit_offset` + access log

**Files:**
- Modify: `backend/api/routers/management.py` (`_require_org_id` 인근)
- Test: `test/backend/management/test_admin_org_scope.py`

- [ ] **Step 1: 실패 테스트 작성** (append)

```python
@pytest.mark.asyncio
async def test_scope_non_admin_returns_own_org():
    own = uuid.uuid4()
    user = SimpleNamespace(id=uuid.uuid4(), role="USER")
    assert await management._scope_org_or_all(user, _MembershipDB(own)) == own


@pytest.mark.asyncio
async def test_scope_admin_no_header_returns_none():
    user = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    assert await management._scope_org_or_all(user, _OrgDB("ACTIVE")) is None


@pytest.mark.asyncio
async def test_scope_admin_header_allows_inactive_org():
    sel = uuid.uuid4()
    management._selected_org_ctx.set(str(sel))
    user = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    assert await management._scope_org_or_all(user, _OrgDB("SUSPENDED")) == sel


def test_clamp_limit_offset():
    assert management._clamp_limit_offset(9999, 0) == (200, 0)
    assert management._clamp_limit_offset(0, 0) == (1, 0)
    assert management._clamp_limit_offset(50, -5) == (50, 0)
    assert management._clamp_limit_offset(50, 10) == (50, 10)


def test_record_admin_read_access_only_for_all_org(monkeypatch):
    events = []
    monkeypatch.setattr(management, "_ACCESS_LOG_SINK", lambda **kw: events.append(kw))
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    management._record_admin_read_access(admin, "created-campaigns", None, limit=50, offset=0)
    management._record_admin_read_access(admin, "created-campaigns", uuid.uuid4(), limit=50, offset=0)
    assert len(events) == 1
    assert events[0]["endpoint"] == "created-campaigns" and events[0]["actor"] == str(admin.id)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k "scope_ or clamp or read_access" -v`
Expected: FAIL — 함수들 없음.

- [ ] **Step 3: 구현**

```python
async def _scope_org_or_all(user, db) -> UUID | None:
    """리스트/집계 3-값 스코프. 비-ADMIN→자기 org / ADMIN+헤더→그 org(read, inactive 허용) / ADMIN+무헤더→None(전체)."""
    if user.role.upper() == "ADMIN":
        sel = _selected_org_ctx.get()
        return await _validated_org(db, sel, require_active=False) if sel else None
    return await require_user_org(user, db)


def _clamp_limit_offset(limit: int, offset: int) -> tuple[int, int]:
    """pagination 상·하한. limit 1..200, offset ≥ 0."""
    return max(1, min(limit, 200)), max(0, offset)


def _ACCESS_LOG_SINK(**kw):  # noqa: N802  (테스트 monkeypatch 주입점)
    # 파일 상단 logger 사용. structlog면 **kw 그대로, stdlib logging이면 logger.info("...", extra=kw)로.
    logger.info("admin_all_org_read", **kw)


def _record_admin_read_access(user, endpoint: str, scope, limit: int, offset: int) -> None:
    """admin 전 org(scope=None) 조회만 경량 access log 1건."""
    if user.role.upper() == "ADMIN" and scope is None:
        _ACCESS_LOG_SINK(actor=str(user.id), endpoint=endpoint, limit=limit, offset=offset)
```
참고: Step 1에서 파일 상단 logger 종류를 확인한다. structlog가 없으면 `import structlog` + `logger = structlog.get_logger(__name__)` 추가(management.py에 이미 있으면 재사용). 기존이 stdlib `logging`이면 `_ACCESS_LOG_SINK`를 `logger.info("admin_all_org_read", extra=kw)`로 바꾼다.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k "scope_ or clamp or read_access" -v`
Expected: PASS (5개)

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "add: _scope_org_or_all + _clamp_limit_offset + 전 org 조회 access log"
```

---

## Task 8: (Phase 2) `/created-campaigns` 인증+스코프+pagination (보안 수정)

**Files:**
- Modify: `backend/api/routers/management.py:497-522` (`created_campaigns`)
- Test: `test/backend/management/test_admin_org_scope.py`

**배경:** 현재 인증 없이(`db`만) 전 org `CreatedCampaign`을 반환하는 테넌트 누출.

- [ ] **Step 1: 실패 테스트 작성** (append) — WHERE 유무 + access log wiring

```python
class _RowsDB:
    """created_campaigns용 — execute(stmt) 캡처. scalar_value는 _validated_org(status)/require_user_org(org) 반환."""
    def __init__(self, rows, scalar_value=None):
        self._rows = rows
        self._scalar_value = scalar_value
        self.stmt = None

    async def scalar(self, *_a, **_k):
        return self._scalar_value

    async def execute(self, stmt, *_a, **_k):
        self.stmt = stmt
        rows = self._rows
        class _R:
            def scalars(self_r):
                class _S:
                    def all(self_s):
                        return rows
                return _S()
        return _R()


def _mk_campaign(tenant, name):
    from datetime import UTC, datetime
    return SimpleNamespace(
        id=uuid.uuid4(), tenant_id=str(tenant), meta_campaign_id="m1", name=name,
        objective="o", ad_account_id="act", daily_budget_krw=0, status="linked",
        execution_mode="manual_link", created_at=datetime.now(UTC), deleted_at=None,
    )


def _app_with(user, db):
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    return app


def test_created_campaigns_requires_auth():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    assert TestClient(app).get("/api/management/created-campaigns").status_code == 401


def test_created_campaigns_admin_all_org_has_no_where():
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    db = _RowsDB([_mk_campaign(uuid.uuid4(), "A"), _mk_campaign(uuid.uuid4(), "B")])
    res = TestClient(_app_with(admin, db)).get("/api/management/created-campaigns")  # 무헤더=전체
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 2 and all("tenant_id" in it for it in items)
    assert db.stmt.whereclause is None  # 전 org = WHERE 없음


def test_created_campaigns_admin_header_scopes_by_org():
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    org = uuid.uuid4()
    db = _RowsDB([_mk_campaign(org, "A")], scalar_value="ACTIVE")  # _validated_org(status)
    res = TestClient(_app_with(admin, db)).get(
        "/api/management/created-campaigns", headers={"X-Org-Id": str(org)}
    )
    assert res.status_code == 200
    assert db.stmt.whereclause is not None  # 특정 org = WHERE 있음


def test_created_campaigns_admin_all_org_records_access_log(monkeypatch):
    """무헤더 admin 전 org 조회 시 access log 1건이 실제로 기록된다."""
    events = []
    monkeypatch.setattr(management, "_ACCESS_LOG_SINK", lambda **kw: events.append(kw))
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    db = _RowsDB([_mk_campaign(uuid.uuid4(), "A")])
    TestClient(_app_with(admin, db)).get("/api/management/created-campaigns")
    assert len(events) == 1 and events[0]["endpoint"] == "created-campaigns"
```
(limit clamp는 Task 7 `test_clamp_limit_offset`로 검증 완료.)

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k created_campaigns -v`
Expected: FAIL — 현재 무인증이라 `requires_auth`가 401을 안 냄.

- [ ] **Step 3: 구현**

`created_campaigns` 교체:

```python
@router.get("/created-campaigns")
async def created_campaigns(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
):
    """앱 생성 캠페인 누적(최신순). 비-ADMIN=자기 org / ADMIN 무헤더=전 org / ADMIN 헤더=그 org."""
    limit, offset = _clamp_limit_offset(limit, offset)
    scope = await _scope_org_or_all(user, db)  # UUID | None(전체)
    _record_admin_read_access(user, "created-campaigns", scope, limit=limit, offset=offset)
    stmt = select(CreatedCampaign)
    if scope is not None:
        stmt = stmt.where(CreatedCampaign.tenant_id == str(scope))
    stmt = (
        stmt.order_by(CreatedCampaign.created_at.desc(), CreatedCampaign.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id),
                "tenant_id": r.tenant_id,
                "meta_campaign_id": r.meta_campaign_id,
                "name": r.name,
                "objective": r.objective,
                "ad_account_id": r.ad_account_id,
                "daily_budget_krw": r.daily_budget_krw,
                "status": r.status,
                "execution_mode": r.execution_mode,
                "created_at": r.created_at.isoformat(),
                "deleted_at": r.deleted_at.isoformat() if r.deleted_at else None,
            }
            for r in rows
        ]
    }
```
참고: `CreatedCampaign.tenant_id`는 문자열 org id(link_simulation 813) → `str(scope)` 비교. `organization_name`은 이번 범위 밖(응답은 tenant_id만).

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k created_campaigns -v`
프론트 소비처 회귀: `grep -n "created-campaigns\|createdCampaigns" frontend/src/lib/api.ts`(응답 shape 동일 items[]).
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "fix: created-campaigns 인증+org 스코프+pagination (테넌트 누출 수정)"
```

---

## Task 9: (Phase 2) `/kpi-overrides` impersonate-only

**Files:**
- Modify: `backend/api/routers/management.py:1581-1603` (`list_kpi_overrides`)
- Test: `test/backend/management/test_admin_org_scope.py`

**결정:** all-org는 campaign_id 키 충돌·shape 파손으로 제외(YAGNI). admin은 **헤더로 org 선택** 시 조회, 무헤더면 빈 결과.

**추가(매트릭스 리뷰 #1):** 같은 org 컨텍스트에서 admin **KPI 저장(PUT)**도 허용한다 — `put_kpi_override`(1614)의 `org_id = await _resolve_org_id(user, db)`(None→409)를 `org_id = await _require_org_id_write(user, db, action="kpi_override")`로 치환(admin 선택 org 저장 + 감사, 비-admin 미소속 409 동일). 이 태스크의 Files에 `put_kpi_override`(1606-1638) 추가, 테스트: admin+헤더 PUT → 그 org에 저장·감사 / admin 무헤더 PUT → 400 / 비-admin 미소속 → 409.

- [ ] **Step 1: 실패 테스트 작성** (append)

```python
class _KpiDB:
    def __init__(self, rows, scalar_value=None):
        self._rows = rows
        self._scalar_value = scalar_value
        self.stmt = None

    async def scalar(self, *_a, **_k):
        return self._scalar_value  # _validated_org(status) 또는 require_user_org(org)

    async def scalars(self, stmt, *_a, **_k):
        self.stmt = stmt
        rows = self._rows
        class _S:
            def all(self_s):
                return rows
        return _S()


def _mk_kpi(org, campaign, cvr=0.1, roas=2.0):
    return SimpleNamespace(organization_id=org, campaign_id=campaign, cvr=cvr, roas=roas)


def test_kpi_overrides_admin_header_scopes_to_org():
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    org = uuid.uuid4()
    db = _KpiDB([_mk_kpi(org, "c1")], scalar_value="ACTIVE")  # _validated_org(status)
    res = TestClient(_app_with(admin, db)).get(
        "/api/management/kpi-overrides", headers={"X-Org-Id": str(org)}
    )
    assert res.status_code == 200
    assert res.json()["overrides"]["c1"]["cvr"] == 0.1
    assert db.stmt.whereclause is not None  # WHERE org 적용


def test_kpi_overrides_admin_no_header_empty():
    admin = SimpleNamespace(id=uuid.uuid4(), role="ADMIN")
    db = _KpiDB([], scalar_value=None)
    res = TestClient(_app_with(admin, db)).get("/api/management/kpi-overrides")  # 무헤더
    assert res.status_code == 200
    assert res.json()["overrides"] == {}
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k kpi_overrides -v`
Expected: FAIL — 현재 admin(멤버십 None) → `{}`, 헤더 무시.

- [ ] **Step 3: 구현**

`list_kpi_overrides` 교체:

```python
@router.get("/kpi-overrides")
async def list_kpi_overrides(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인별 수동 KPI. 비-ADMIN=자기 org / ADMIN=X-Org-Id로 선택한 org(미선택 시 빈 결과). all-org 미지원(campaign_id 충돌)."""
    scope = await _scope_org_or_all(user, db)  # UUID | None
    if scope is None:  # admin 무헤더 — impersonate 미선택
        return {"overrides": {}}
    rows = (
        await db.scalars(
            select(CampaignKpiOverride).where(CampaignKpiOverride.organization_id == scope)
        )
    ).all()
    return {
        "overrides": {
            r.campaign_id: {
                **({"cvr": r.cvr} if r.cvr is not None else {}),
                **({"roas": r.roas} if r.roas is not None else {}),
            }
            for r in rows
        }
    }
```
참고: 비-ADMIN 미소속은 `_scope_org_or_all`→`require_user_org`가 409(기존 `_resolve_org_id`는 None→빈결과였음). 이 변경은 다른 management 엔드포인트와 일관(미소속 409). 회귀는 `-k kpi`로 확인.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_admin_org_scope.py -k kpi_overrides -v`
기존 회귀: `cd backend && uv run pytest ../test/backend/management -k kpi -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py test/backend/management/test_admin_org_scope.py
git commit -m "add: kpi-overrides admin impersonate(X-Org-Id) 조회"
```

---

## Task 10: (프론트) `request()` management 한정 `X-Org-Id` + adminOrgId 유틸

**Files:**
- Modify: `frontend/src/lib/api.ts` (`request` 헬퍼 + 유틸)

- [ ] **Step 1: adminOrgId 유틸 추가**

`api.ts` (getToken 인근):
```ts
// admin이 impersonate로 선택한 org id (management 요청에만 X-Org-Id로 실림). sessionStorage=탭 종료 시 소멸.
export function getAdminOrgId(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem("adminOrgId");
}
export function setAdminOrgId(orgId: string | null): void {
  if (typeof window === "undefined") return;
  if (orgId) window.sessionStorage.setItem("adminOrgId", orgId);
  else window.sessionStorage.removeItem("adminOrgId");
}
```
로그아웃/토큰 clear 지점에서 `setAdminOrgId(null)` 호출 추가.

- [ ] **Step 2: request()에서 management 경로 한정 부착**

`request<T>(path, init)` authHeader 구성부:
```ts
  const orgId = getAdminOrgId();
  // 계약: path는 `/api` 이후 상대경로. management 요청 & adminOrgId 있을 때만 부착.
  // (adminOrgId는 admin 전용 picker에서만 set·비-admin 로그인 시 clear되므로 role 게이팅은 set 측 — Task 11.)
  const orgHeader: Record<string, string> =
    orgId && path.startsWith("/management") ? { "X-Org-Id": orgId } : {};
```
`fetch(...)`의 `headers`에 `...orgHeader` 병합.

- [ ] **Step 3: 빌드·린트**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과.

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/lib/api.ts
git commit -m "add: 프론트 request() management 한정 X-Org-Id + adminOrgId 유틸"
```

---

## Task 11: (프론트) admin 게이팅 + org 선택 드롭다운

**Files:**
- Modify: `frontend/src/components/AuthProvider.tsx` — role≠ADMIN이면 `setAdminOrgId(null)`
- Create: `frontend/src/components/manage/AdminOrgPicker.tsx`
- Modify: management 화면 상단(관리 진입 레이아웃/헤더 — 구현 시 진입점 확인)

- [ ] **Step 1: AuthProvider clear 경로 확인 후 배치**

`AuthProvider`에서 유저 상태가 확정/변경되는 **모든 경로**(초기 로드, 로그인 성공, 유저 전환, 로그아웃)를 확인한다. role이 확정되는 단일 지점(예: user state effect)이 있으면 거기에, 없으면 각 경로에 아래를 넣는다:
```ts
import { setAdminOrgId } from "@/lib/api";
// user(role) 확정/변경 시:
if (!user || user.role?.toUpperCase() !== "ADMIN") {
  setAdminOrgId(null);  // 비-admin은 impersonation 힌트 보유 금지(stale 방지)
}
```
확인 사항(체크): (1) 로그아웃 시 clear, (2) 다른 계정 로그인 시 clear, (3) 초기 비-admin 로드 시 clear — 셋 다 실제로 걸리는지 코드 경로로 확인.

- [ ] **Step 2: AdminOrgPicker 작성**

```tsx
// admin이 management를 볼 org를 고르는 드롭다운 — "전체"면 X-Org-Id 미전송(전 org 뷰).
"use client";
import { useEffect, useState } from "react";
import { request, getAdminOrgId, setAdminOrgId } from "@/lib/api";

type Org = { id: string; name: string };

export function AdminOrgPicker() {
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [sel, setSel] = useState<string>(getAdminOrgId() ?? "");
  useEffect(() => {
    request<{ organizations?: Org[] } | Org[]>("/admin/organizations")
      .then((r) => setOrgs(Array.isArray(r) ? r : (r.organizations ?? [])))
      .catch(() => setOrgs([]));
  }, []);
  return (
    <select
      value={sel}
      onChange={(e) => {
        const v = e.target.value;
        setSel(v);
        setAdminOrgId(v || null);
        window.location.reload();
      }}
      className="rounded border px-2 py-1 text-sm"
    >
      <option value="">전체 (all orgs)</option>
      {orgs.map((o) => (
        <option key={o.id} value={o.id}>{o.name}</option>
      ))}
    </select>
  );
}
```
참고: `/admin/organizations` 실제 응답 shape를 확인해 매핑 조정.

- [ ] **Step 3: 관리 화면에 admin일 때만 렌더 + KPI 영역 안내**

관리 화면 상단에서 `useAuth()` role이 ADMIN일 때만 `<AdminOrgPicker />` 렌더.
**KPI override 영역**: admin이면서 org 미선택("전체") 상태에선 KPI override 섹션을 **숨기거나 "조직을 선택하세요" 안내**를 표시(kpi-overrides는 impersonate-only라 무헤더면 빈 결과 → "데이터 없음" 혼동 방지).

- [ ] **Step 4: 빌드·린트**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과.

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/AuthProvider.tsx frontend/src/components/manage/AdminOrgPicker.tsx frontend/src/app
git commit -m "add: admin org 선택 드롭다운 + 비-admin adminOrgId 게이팅"
```

---

## Task 12: 통합 검증

- [ ] **Step 1: 백엔드 전체 management 테스트**

Run: `cd backend && uv run pytest ../test/backend/management -v`
Expected: 신규 + 기존 전부 PASS. 실패 시 해당 태스크 복귀.

- [ ] **Step 2: Ruff 최종**

Run: `cd backend && uv run ruff format . && uv run ruff check .`
Expected: clean.

- [ ] **Step 3: 프론트 빌드**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과.

- [ ] **Step 4: (선택) Claude Preview 화면 확인**

admin 로그인 → 드롭다운 "전체" 시 created-campaigns 전 org, 특정 org 선택 시 그 org만·kpi-overrides 표시. 비-admin은 자기 org만.

---

## 완료 기준 (spec 대응)

- Phase 0 매트릭스 + write 체크박스(§5·§6.1) — Task 1.
- ContextVar+yield 의존성·reset(§6.2) — Task 2.
- `_validated_org(require_active)`(§6.4) — Task 3.
- `_require_org_id` role 인지 + 안전장치 ①②③(§4·§6.3) — Task 4.
- meta_connect 대리 차단(§6.1) — Task 5.
- impersonation 감사(안전장치 ④, §6.5) `_require_org_id_write` seam + 치환 정적 대조 — Task 6.
- `_scope_org_or_all`+clamp+access log(§6.5·§6.6) — Task 7.
- created-campaigns 전 org+pagination+안정정렬(§6.6)+보안 수정+access log wiring 테스트 — Task 8.
- kpi-overrides impersonate(§6.6, all-org YAGNI 제외) — Task 9.
- 프론트 management 한정 헤더+adminOrgId(§9) — Task 10.
- admin 게이팅(전 경로 clear)+picker+KPI 안내 — Task 11. (organization_name 표시는 범위 제외 — 후속.)
- 테스트(§10) — 각 Task + Task 12.
