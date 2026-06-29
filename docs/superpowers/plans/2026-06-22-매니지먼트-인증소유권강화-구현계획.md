# 매니지먼트 인증·소유권 강화 (Vuln 3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 🅱 소유 매니지먼트 상태변경 엔드포인트 13개에 JWT 인증 + org 소유권 검증을 추가해 미인증·cross-tenant 조작을 차단한다.

**Architecture:** `backend/api/routers/management.py`의 🅱 핸들러 시그니처에만 `get_current_user`/`get_db` 의존성을 주입하고(라우터 레벨 금지 — 🅰 엔드포인트 보호), 공용 헬퍼 4종으로 org 도출·캠페인 소유권·광고계정 도출을 캡슐화한다. 데이터 모델·Alembic 무변경(기존 `CreatedCampaign.tenant_id`·`MetaConnection.ad_account_id`·`EscalationRun.tenant_id` 재사용).

**Tech Stack:** FastAPI, SQLAlchemy(async), Pydantic v2, pytest + FastAPI `TestClient` + `app.dependency_overrides`.

**참조 스펙:** `docs/superpowers/specs/2026-06-22-management-authz-hardening-design.md`

---

## File Structure

- Modify: `backend/api/routers/management.py` — 헬퍼 4종 추가 + 13개 핸들러 의존성/스코핑 수정
- Modify: `backend/domain/management/escalation.py` — `EscalationController.get_run` 읽기 접근자 추가
- Create: `backend/tests/management/test_authz_hardening.py` — 헬퍼 단위 + 엔드포인트 인증/소유권 테스트
- Create: `docs/management/oauth-state-csrf-handoff.md` — Vuln 2 🅰 핸드오프 문서

**대상 13개 엔드포인트(모두 management.py):** `/execute`, `/regenerate`, `/campaigns/create-proposal`, `/campaign-proposals/from-candidate`, `/ad-image`, `DELETE /campaigns/{id}`, `/campaigns/{id}/activate`, `/campaigns/{id}/pause`, `/campaigns/{id}/sync`, `/budget/limit`, `/re-evaluate`, `/re-evaluate/executed`, `/re-evaluate/rejected`.

**무변경(비목표):** `/approve`(🅰), OAuth `/meta/connect`·`/meta/callback`(🅰), 읽기 전용 GET, `core/models.py`·Alembic.

---

## Task 1: 공용 헬퍼 + 단위 테스트

**Files:**
- Modify: `backend/api/routers/management.py:27` (import), `:1223` 직후(헬퍼 추가)
- Test: `backend/tests/management/test_authz_hardening.py`

- [ ] **Step 1: import에 `MetaConnection` 추가**

`management.py:27` 을 다음으로 교체:

```python
from core.models import (
    CampaignKpiOverride,
    CreatedCampaign,
    MetaConnection,
    OrganizationMember,
    User,
)
```

- [ ] **Step 2: 헬퍼 4종 추가**

`management.py`의 `_created_campaign_row` 함수 정의 바로 뒤(현재 ~line 1223)에 추가:

```python
def _is_demo_campaign(campaign_id: str) -> bool:
    """campaign_id가 데모 픽스처(_CAMPAIGNS_DEMO)에 존재하는지."""
    return any(cid == campaign_id for cid, *_ in _CAMPAIGNS_DEMO)


async def _require_org_id(user: User, db: AsyncSession) -> UUID:
    """로그인 사용자의 소속 org — 없으면 409."""
    org_id = await _resolve_org_id(user, db)
    if org_id is None:
        raise HTTPException(409, "소속 조직이 없습니다 — 조직 연결 후 시도하세요.")
    return org_id


async def _require_owned_campaign(
    db: AsyncSession, org_id: UUID, campaign_id: str
) -> CreatedCampaign | None:
    """DB 적재 캠페인은 tenant 소유 검증. DB 행 없음은 mock/demo fixture로 확인된 경우에만 None 허용."""
    row = await _created_campaign_row(db, campaign_id)
    if row is not None:
        if row.tenant_id != str(org_id):
            raise HTTPException(403, "다른 조직의 캠페인입니다.")
        return row
    if getattr(settings, "use_mock", True) and _is_demo_campaign(campaign_id):
        return None
    raise HTTPException(404, "캠페인을 찾을 수 없습니다.")


async def _require_ad_account(db: AsyncSession, org_id: UUID) -> str:
    """org의 Meta 광고계정 — 연결에서 도출. live 미연결이면 데모 폴백 금지(fail-closed)."""
    conn = await db.scalar(
        select(MetaConnection).where(MetaConnection.organization_id == org_id)
    )
    if conn is not None and conn.ad_account_id:
        return conn.ad_account_id
    if getattr(settings, "use_mock", True):
        return _DEMO_AD_ACCOUNT
    raise HTTPException(409, "Meta 광고계정 연결이 필요합니다 — 연결 후 시도하세요.")
```

- [ ] **Step 3: 테스트 파일 생성(공용 Fake + 헬퍼 실패 테스트)**

`backend/tests/management/test_authz_hardening.py` 생성:

```python
# 🅱 매니지먼트 인증·소유권 강화(Vuln 3) — 헬퍼 단위 + 엔드포인트 인증/소유권
import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db


class _FakeScalars:
    def __init__(self, v):
        self._v = v

    def first(self):
        return self._v

    def all(self):
        return [self._v] if self._v is not None else []


class _FakeResult:
    def __init__(self, v):
        self._v = v

    def scalars(self):
        return _FakeScalars(self._v)


class _FakeDB:
    """db.scalar는 쿼리 대상 테이블로 분기, db.execute는 캠페인 행을 반환."""

    def __init__(self, *, org_id=None, conn=None, campaign=None):
        self._org_id = org_id
        self._conn = conn
        self._campaign = campaign

    async def scalar(self, stmt, *a, **k):
        s = str(stmt)
        if "organization_members" in s:
            return self._org_id
        if "meta_connections" in s:
            return self._conn
        return None

    async def execute(self, stmt, *a, **k):
        return _FakeResult(self._campaign)

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def delete(self, obj):
        pass


@pytest.mark.asyncio
async def test_require_org_id_raises_409_without_org():
    db = _FakeDB(org_id=None)
    with pytest.raises(HTTPException) as exc:
        await management._require_org_id(SimpleNamespace(id=uuid.uuid4()), db)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_require_owned_campaign_cross_tenant_403():
    org = uuid.uuid4()
    other = uuid.uuid4()
    db = _FakeDB(campaign=SimpleNamespace(tenant_id=str(other), daily_budget_krw=1000, name="x"))
    with pytest.raises(HTTPException) as exc:
        await management._require_owned_campaign(db, org, "camp_x")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_owned_campaign_owned_returns_row():
    org = uuid.uuid4()
    db = _FakeDB(campaign=SimpleNamespace(tenant_id=str(org), daily_budget_krw=1000, name="x"))
    row = await management._require_owned_campaign(db, org, "camp_x")
    assert row.tenant_id == str(org)


@pytest.mark.asyncio
async def test_require_owned_campaign_unknown_404(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    db = _FakeDB(campaign=None)  # DB 행 없음 + 데모 픽스처에 없는 id
    with pytest.raises(HTTPException) as exc:
        await management._require_owned_campaign(db, uuid.uuid4(), "totally_unknown")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_require_owned_campaign_demo_fixture_allows_none(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    db = _FakeDB(campaign=None)
    demo_id = management._CAMPAIGNS_DEMO[0][0]  # 픽스처에 존재하는 id
    assert await management._require_owned_campaign(db, uuid.uuid4(), demo_id) is None


@pytest.mark.asyncio
async def test_require_ad_account_live_failclosed_without_connection(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", False, raising=False)
    db = _FakeDB(conn=None)
    with pytest.raises(HTTPException) as exc:
        await management._require_ad_account(db, uuid.uuid4())
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_require_ad_account_mock_falls_back_to_demo(monkeypatch):
    monkeypatch.setattr(management.settings, "use_mock", True, raising=False)
    db = _FakeDB(conn=None)
    assert await management._require_ad_account(db, uuid.uuid4()) == management._DEMO_AD_ACCOUNT
```

- [ ] **Step 4: 헬퍼 테스트 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py -v`
Expected: 7개 PASS

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_authz_hardening.py
git commit -m "add: 매니지먼트 인증·소유권 공용 헬퍼(Vuln3) + 단위 테스트"
```

---

## Task 2: EscalationController.get_run 접근자

**Files:**
- Modify: `backend/domain/management/escalation.py` (`EscalationController`에 메서드 추가, ~line 153 `re_evaluate` 정의 앞)
- Test: `backend/tests/management/test_authz_hardening.py`

- [ ] **Step 1: 실패 테스트 추가**

`test_authz_hardening.py` 끝에 추가:

```python
@pytest.mark.asyncio
async def test_escalation_controller_get_run_reads_store():
    from domain.management.escalation import EscalationController, EscalationRun

    run = EscalationRun(tenant_id="org_1", ad_account_id="act_1", campaign_id="camp_1")

    class _Store:
        async def get_by_run_id(self, run_id):
            return run if run_id == run.run_id else None

    ctrl = EscalationController(
        store=_Store(), detector=object(), agent=object(), audit=object()
    )
    assert (await ctrl.get_run(run.run_id)) is run
    assert (await ctrl.get_run("nope")) is None
```

- [ ] **Step 2: 실행 — 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py::test_escalation_controller_get_run_reads_store -v`
Expected: FAIL with `AttributeError: 'EscalationController' object has no attribute 'get_run'`

- [ ] **Step 3: get_run 메서드 추가**

`escalation.py`의 `EscalationController` 안, `re_evaluate` 메서드 정의 바로 앞에 추가:

```python
    async def get_run(self, run_id: str):
        """run_id로 사다리 run 조회 — 라우터의 tenant 소유 검증용(읽기 전용)."""
        return await self._store.get_by_run_id(run_id)
```

- [ ] **Step 4: 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py::test_escalation_controller_get_run_reads_store -v`
Expected: PASS

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/escalation.py backend/tests/management/test_authz_hardening.py
git commit -m "add: EscalationController.get_run 읽기 접근자(run 소유 검증용)"
```

---

## Task 3: 제안 생산 엔드포인트 — /execute · /regenerate · create-proposal · from-candidate

**Files:**
- Modify: `backend/api/routers/management.py` (4개 핸들러)
- Test: `backend/tests/management/test_authz_hardening.py`

- [ ] **Step 1: `/execute` 수정**

`@router.post("/execute")` 핸들러 시그니처와 도입부를 교체:

```python
@router.post("/execute")
async def execute(
    body: ExecuteRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """🅱 executor — 승인 후 4단계 재검증 + 멱등 실행. 모든 지출 단일 경로."""
    org_id = await _require_org_id(user, db)
    if body.proposal.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 제안은 실행할 수 없습니다.")
    if body.approved_action.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 승인은 실행할 수 없습니다.")
    result = await _get_executor().execute(body.approved_action, body.proposal)
```

(이하 `if body.proposal.action_type == "CREATE_CAMPAIGN":` 부터는 그대로 유지.)

- [ ] **Step 2: `/regenerate` 수정**

핸들러 시그니처와 context 생성부를 교체:

```python
@router.post("/regenerate")
async def regenerate(
    body: RegenerateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """🅱 재생성 agent — 진단 수신 → 4-3 위임 생성 → guard → AWAITING_SELECTION."""
    org_id = await _require_org_id(user, db)
    if body.diagnosis.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 진단으로 재생성할 수 없습니다.")
    ad_account = await _require_ad_account(db, org_id)
    agent = build_regeneration_agent()
    context = RemediationContext(
        ad_account_id=ad_account,
        target_object_ids=(body.diagnosis.campaign_id,),
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        run_days=7,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    outcome = await agent.rank(body.diagnosis, context)
```

(이하 outcome 분기는 그대로 유지.)

- [ ] **Step 3: `/campaigns/create-proposal` 수정**

시그니처와 `ad_account`/`tenant_id` 도출부를 교체. 핸들러를 다음으로 수정:

```python
@router.post("/campaigns/create-proposal")
async def create_campaign_proposal(
    body: CreateCampaignRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """폼 입력 → CREATE_CAMPAIGN 제안(Tier 3) 패키징."""
    org_id = await _require_org_id(user, db)
    policy = await get_campaign_policy(build_reader(settings))
    min_budget = min_daily_budget_for(body.objective, policy)
    if body.daily_budget_krw < min_budget:
        raise HTTPException(
            status_code=422,
            detail=f"{body.objective} 캠페인의 최소 일예산은 ₩{min_budget:,}입니다 (Meta 정책).",
        )
    now = datetime.now(UTC)
    ad_account = await _require_ad_account(db, org_id)
    tenant_id = str(org_id)
```

그리고 같은 핸들러 안의 `CampaignConfig(... tenant_id=TENANT_ID ...)` 를 `tenant_id=tenant_id` 로,
`ActionProposal(... tenant_id=TENANT_ID ...)` 를 `tenant_id=tenant_id` 로 교체한다(각 1곳).

- [ ] **Step 4: `/campaign-proposals/from-candidate` 수정**

시그니처를 교체:

```python
@router.post("/campaign-proposals/from-candidate")
async def from_candidate(
    body: FromCandidateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

핸들러 본문에서 `ad_account = _resolve_ad_account()` (현재 line ~1120) 를 다음으로 교체:

```python
    org_id = await _require_org_id(user, db)
    ad_account = await _require_ad_account(db, org_id)
    tenant_id = str(org_id)
```

그리고 같은 핸들러의 `CampaignConfig(... tenant_id=TENANT_ID ...)` 와 `ActionProposal(... tenant_id=TENANT_ID ...)` 를 각각 `tenant_id=tenant_id` 로 교체(각 1곳).

> 주의: `org_id`/`ad_account` 도출은 외부 호출(generator·S3·upload) 이후가 아니라 **그 앞**에 두어도
> 무방하나, 위 위치(기존 `ad_account` 라인 대체)면 최소 변경이다. 인증 의존성은 시그니처에서 이미 강제된다.

- [ ] **Step 5: 인증 테스트 추가**

`test_authz_hardening.py` 끝에 추가:

```python
def _client_no_auth():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app, raise_server_exceptions=False)


def test_execute_requires_auth():
    res = _client_no_auth().post("/api/management/execute", json={})
    assert res.status_code == 401


def test_regenerate_requires_auth():
    res = _client_no_auth().post("/api/management/regenerate", json={})
    assert res.status_code == 401


def test_create_proposal_requires_auth():
    res = _client_no_auth().post("/api/management/campaigns/create-proposal", json={})
    assert res.status_code == 401


def test_from_candidate_requires_auth():
    res = _client_no_auth().post(
        "/api/management/campaign-proposals/from-candidate", json={}
    )
    assert res.status_code == 401
```

- [ ] **Step 6: 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py -v`
Expected: 모두 PASS (401은 인증 의존성이 body 검증보다 먼저 동작)

- [ ] **Step 7: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_authz_hardening.py
git commit -m "edit: 제안 생산 엔드포인트 인증+tenant 스코핑(execute/regenerate/create-proposal/from-candidate)"
```

---

## Task 4: /ad-image — 인증

**Files:**
- Modify: `backend/api/routers/management.py` (`upload_ad_image`)
- Test: `backend/tests/management/test_authz_hardening.py`

- [ ] **Step 1: 시그니처에 인증 추가**

```python
@router.post("/ad-image")
async def upload_ad_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """광고 소재 이미지를 Meta(/adimages)에 업로드 → image_hash 반환. 무과금(자산 등록)."""
    writer = build_writer(settings)
```

(본문 나머지 변경 없음. 이미지 업로드는 tenant 귀속이 없는 자산 등록이라 인증만 강제.)

- [ ] **Step 2: 인증 테스트 추가**

`test_authz_hardening.py` 끝에 추가:

```python
def test_ad_image_requires_auth():
    res = _client_no_auth().post("/api/management/ad-image")
    assert res.status_code == 401
```

- [ ] **Step 3: 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py::test_ad_image_requires_auth -v`
Expected: PASS

- [ ] **Step 4: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_authz_hardening.py
git commit -m "edit: /ad-image 인증 추가"
```

---

## Task 5: 캠페인 대상 엔드포인트 — delete · activate · pause · sync (인증 + 소유권)

**Files:**
- Modify: `backend/api/routers/management.py` (4개 핸들러)
- Test: `backend/tests/management/test_authz_hardening.py`

- [ ] **Step 1: `DELETE /campaigns/{id}` 수정**

```python
@router.delete("/campaigns/{campaign_id}")
async def delete_campaign(
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 삭제 — 자식 광고세트·광고도 함께. LIVE 모드에서만 실제 Meta 삭제(그 외 무동작)."""
    org_id = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_id, campaign_id)
    writer = build_writer(settings)
    result = await writer.delete_campaign(campaign_id, idem_key=f"del_{campaign_id}")
```

(이하 소프트삭제 로직 그대로 유지.)

- [ ] **Step 2: `/campaigns/{id}/activate` 수정**

시그니처와 도입부를 교체:

```python
@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(
    campaign_id: str,
    body: ActivateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """게재 시작 — Meta 선불 잔액 게이트 → spend_cap → 캠페인·세트·광고 ACTIVE. 실과금 시작점."""
    org_id = await _require_org_id(user, db)
    row = await _require_owned_campaign(db, org_id, campaign_id)
    commit = body.commit_krw or (row.daily_budget_krw if row else 0)
```

그리고 같은 핸들러 안의 `ad_account = _resolve_ad_account()` (현재 ~line 1287) 를
`ad_account = await _require_ad_account(db, org_id)` 로,
`ActionProposal(... tenant_id=TENANT_ID ...)` 를 `tenant_id=str(org_id)` 로 교체.

> 참고: 기존 `row = await _created_campaign_row(db, campaign_id)` 줄은 위 `_require_owned_campaign`
> 반환으로 대체되므로 제거한다(중복 조회 방지). `row`는 demo 픽스처면 None일 수 있어 기존 `if row else 0` 유지.

- [ ] **Step 3: `/campaigns/{id}/pause` 수정**

```python
@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """캠페인 즉시 일시중지(PAUSED) — 게재·과금 중단."""
    org_id = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_id, campaign_id)
    now = datetime.now(UTC)
    ad_account = await _require_ad_account(db, org_id)
```

그리고 같은 핸들러의 `ActionProposal(... tenant_id=TENANT_ID ...)` 를 `tenant_id=str(org_id)` 로 교체.

- [ ] **Step 4: `/campaigns/{id}/sync` 수정 — 쿼리 org_id 제거**

```python
@router.get("/campaigns/{campaign_id}/sync")
async def sync_campaign(
    campaign_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Meta 누적 소진액 → 크레딧 차감 정산(증분) + 자동 종료 상태 반영."""
    org_uuid = await _require_org_id(user, db)
    await _require_owned_campaign(db, org_uuid, campaign_id)
    org_id = str(org_uuid)
    reader = build_reader(settings)
```

(이하 본문에서 기존 `org_id`(쿼리) 사용처는 그대로 — 이제 JWT 도출값을 가리킨다. 기존
`row = await _created_campaign_row(db, campaign_id)` 줄은 유지해도 무방하나, 소유권 검증이 이미
같은 행을 확인하므로 남겨둔다.)

> **보안 포인트:** 시그니처에서 `org_id: str = DEMO_ORG_ID` 쿼리 파라미터를 **제거**한다 — 공격자 통제 제거.
>
> **import 정리:** 이 변경으로 `DEMO_ORG_ID`(management.py:23 `from api.routers.billing import DEMO_ORG_ID, get_billing_service`)가 미사용이 되면 ruff `F401`이 발생한다. 다른 사용처가 없으면 import에서 `DEMO_ORG_ID`만 제거하고 `get_billing_service`는 유지한다(`uv run ruff check . --fix`가 처리하나, 공유 파일이므로 제거 전 다른 참조가 없는지 grep으로 확인).

- [ ] **Step 5: 인증·소유권 테스트 추가**

`test_authz_hardening.py` 끝에 추가:

```python
def _client_with(org_id, *, campaign=None, conn=None, use_mock=True, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(management.settings, "use_mock", use_mock, raising=False)
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(
        org_id=org_id, campaign=campaign, conn=conn
    )
    return TestClient(app, raise_server_exceptions=False)


def test_delete_requires_auth():
    res = _client_no_auth().delete("/api/management/campaigns/camp_x")
    assert res.status_code == 401


def test_sync_requires_auth():
    res = _client_no_auth().get("/api/management/campaigns/camp_x/sync")
    assert res.status_code == 401


def test_delete_cross_tenant_403(monkeypatch):
    org = uuid.uuid4()
    other = uuid.uuid4()
    campaign = SimpleNamespace(tenant_id=str(other), daily_budget_krw=1000, name="x")
    client = _client_with(org, campaign=campaign, monkeypatch=monkeypatch)
    res = client.delete("/api/management/campaigns/camp_x")
    assert res.status_code == 403


def test_sync_unknown_campaign_404(monkeypatch):
    org = uuid.uuid4()
    client = _client_with(org, campaign=None, use_mock=True, monkeypatch=monkeypatch)
    res = client.get("/api/management/campaigns/totally_unknown/sync")
    assert res.status_code == 404
```

- [ ] **Step 6: 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py -v`
Expected: 모두 PASS

- [ ] **Step 7: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_authz_hardening.py
git commit -m "edit: 캠페인 대상 엔드포인트 인증+소유권(delete/activate/pause/sync), sync 쿼리 org_id 제거"
```

---

## Task 6: /budget/limit — 인증

**Files:**
- Modify: `backend/api/routers/management.py` (`set_budget_limit`)
- Test: `backend/tests/management/test_authz_hardening.py`

> **스펙 편차(확인 필요):** 스펙 표 row 10은 "인증 + 내 org tenant"지만, 예산은 `_BUDGET`(인메모리,
> `TENANT_ID` 키)으로 보관하고 **범위 밖인 GET /budget(`_budget_status`)** 가 같은 키를 읽는다. 키를
> `str(org_id)`로 즉시 전환하면 GET /budget 표시가 깨진다. 따라서 이번 작업은 **인증(미인증 차단)** 을
> 우선 적용하고, per-org 키 전환은 GET /budget 동시 수정이 필요한 후속으로 분리한다. 잔여 리스크:
> 인증된 사용자가 데모 공용 예산 한도를 바꿀 수 있음(인메모리 데모 한계, 신규 취약점 아님).

- [ ] **Step 1: 시그니처에 인증 추가**

```python
@router.post("/budget/limit")
async def set_budget_limit(
    body: BudgetLimitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """예산 한도 설정 — 변경 후 경고 레벨(decision)이 즉시 반영(인메모리)."""
    await _require_org_id(user, db)
    _BUDGET.set_limit(TENANT_ID, body.limit_krw)
    return await _budget_status()
```

- [ ] **Step 2: 인증 테스트 추가**

```python
def test_budget_limit_requires_auth():
    res = _client_no_auth().post("/api/management/budget/limit", json={"limit_krw": 1000})
    assert res.status_code == 401
```

- [ ] **Step 3: 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py::test_budget_limit_requires_auth -v`
Expected: PASS

- [ ] **Step 4: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_authz_hardening.py
git commit -m "edit: /budget/limit 인증 추가(per-org 키 전환은 후속)"
```

---

## Task 7: 에스컬레이션 — /re-evaluate · /re-evaluate/executed · /re-evaluate/rejected

**Files:**
- Modify: `backend/api/routers/management.py` (3개 핸들러)
- Test: `backend/tests/management/test_authz_hardening.py`

- [ ] **Step 1: `/re-evaluate` 수정 — tenant를 내 org로 강제**

```python
@router.post("/re-evaluate")
async def re_evaluate(
    body: ReEvaluateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """사다리 1회 재평가 — 개시/다음단계 제안 / 보류(PENDING) / 회복 / 소진을 반환."""
    org_id = await _require_org_id(user, db)
    ad_account = await _require_ad_account(db, org_id)
    outcome = await _get_escalation().re_evaluate(
        str(org_id), ad_account, body.campaign_id, now=_now_or(body.now)
    )
    return _escalation_payload(outcome)
```

- [ ] **Step 2: `/re-evaluate/executed` 수정 — run 소유 검증**

```python
@router.post("/re-evaluate/executed")
async def mark_rung_executed(
    body: RungOutcomeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 단계가 집행됐음을 사다리에 알린다 (다음 재평가에서 회복 판정 가능)."""
    org_id = await _require_org_id(user, db)
    run = await _get_escalation().get_run(body.run_id)
    if run is None:
        raise HTTPException(404, "run을 찾을 수 없습니다.")
    if run.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 run입니다.")
    await _get_escalation().on_executed(
        body.run_id, now=_now_or(body.now), approval_id=body.approval_id
    )
    return {"run_id": body.run_id, "rung_status": "executed"}
```

- [ ] **Step 3: `/re-evaluate/rejected` 수정 — run 소유 검증**

```python
@router.post("/re-evaluate/rejected")
async def mark_rung_rejected(
    body: RungOutcomeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 단계가 거절됐음을 알린다 (다음 재평가에서 즉시 다음 단계로 에스컬레이션)."""
    org_id = await _require_org_id(user, db)
    run = await _get_escalation().get_run(body.run_id)
    if run is None:
        raise HTTPException(404, "run을 찾을 수 없습니다.")
    if run.tenant_id != str(org_id):
        raise HTTPException(403, "다른 조직의 run입니다.")
    await _get_escalation().on_rejected(body.run_id)
    return {"run_id": body.run_id, "rung_status": "rejected"}
```

- [ ] **Step 4: 인증·소유권 테스트 추가**

```python
def test_re_evaluate_requires_auth():
    res = _client_no_auth().post("/api/management/re-evaluate", json={})
    assert res.status_code == 401


def test_rung_executed_cross_tenant_403(monkeypatch):
    org = uuid.uuid4()
    other = uuid.uuid4()
    run = SimpleNamespace(tenant_id=str(other), run_id="esc_1")
    monkeypatch.setattr(
        management, "_get_escalation",
        lambda: SimpleNamespace(get_run=lambda rid: _async_return(run)),
    )
    client = _client_with(org, monkeypatch=monkeypatch)
    res = client.post("/api/management/re-evaluate/executed", json={"run_id": "esc_1"})
    assert res.status_code == 403
```

그리고 파일 상단 import 아래에 헬퍼 추가:

```python
def _async_return(value):
    async def _coro(*a, **k):
        return value
    return _coro()
```

> 주의: `get_run`은 `await` 되므로 람다가 코루틴을 반환해야 한다. `_async_return(run)`이 매 호출 새
> 코루틴을 만들도록 `lambda rid: _async_return(run)` 형태를 쓴다.

- [ ] **Step 5: 실행 — 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_authz_hardening.py -v`
Expected: 모두 PASS

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/tests/management/test_authz_hardening.py
git commit -m "edit: re-evaluate 계열 인증+tenant 강제+run 소유 검증"
```

---

## Task 8: Vuln 2 핸드오프 문서 (🅰)

**Files:**
- Create: `docs/management/oauth-state-csrf-handoff.md`

- [ ] **Step 1: 문서 작성**

`docs/management/oauth-state-csrf-handoff.md` 생성:

```markdown
# [🅰 핸드오프] OAuth state 미검증 — Meta 연결 CSRF/토큰 주입 (Vuln 2)

> 출처: 2026-06-22 보안 리뷰. 소유: 🅰(OAuth/connect/callback). 🅱는 코드 미수정, 본 문서로 전달.

## 문제
- `/meta/connect`(management.py:1548)가 `state="{org}:{nonce}"`를 만들지만 nonce를 서버에 저장하지 않음.
- `/meta/callback`(management.py:1578)은 미인증이며 `state.split(":",1)[0]`(1602)로 파싱한 org를 그대로 신뢰,
  교환한 장기 토큰을 그 org로 `upsert`(connection_repository.py, org_id 단일 키 → 기존 토큰 덮어쓰기).

## 영향
- OAuth CSRF/토큰 주입: 공격자의 Meta 토큰을 임의 org에 바인딩 → 해당 org의 캠페인 읽기/쓰기가
  공격자 자산으로 흐름.
- 임의 org의 기존 Meta 연결 토큰 덮어쓰기(자격 탈취).

## 권장 수정
1. connect 시점에 인증 사용자/org에 바인딩된 **single-use·TTL nonce를 서버에 저장**(예: 신규 테이블 또는
   기존 저장소). state는 불투명 토큰만 운반.
2. callback에서 nonce를 조회·소진(consume) 검증하고, **저장된 레코드의 org**를 사용. raw `state`의 org는
   신뢰하지 않는다.
3. callback의 org 도출을 평문 파싱(`state.split`)에서 제거.

## 비고
- DB 테이블 추가가 필요하면 `core/models.py`·Alembic 변경이라 사전 공지 + 양측 합의 필요(공통부 규칙).
```

- [ ] **Step 2: 커밋**

```bash
git add docs/management/oauth-state-csrf-handoff.md
git commit -m "add: Vuln2 OAuth state CSRF 🅰 핸드오프 문서"
```

---

## Task 9: 전체 검증 + 회귀 확인

**Files:** 없음(검증만)

- [ ] **Step 1: 매니지먼트 전체 테스트 실행**

Run: `cd backend && uv run pytest tests/management/ -v`
Expected: 전체 PASS. 기존 라우터 테스트가 인증 추가로 깨지면(예: `test_management_router.py`,
`test_budget_router.py`, `test_create_proposal_router.py`, `test_activation.py`, `test_campaign_chain.py`)
해당 테스트가 수정 대상 엔드포인트를 호출하는 경우 `app.dependency_overrides[get_current_user]`/`get_db`
오버라이드(Task 1 `_FakeDB` 패턴, `test_meta_oauth_router.py` 참고)를 추가해 고친다.

- [ ] **Step 2: 깨진 기존 테스트 수정(있으면)**

각 실패 테스트에 대해 `get_current_user`/`get_db` 의존성 오버라이드를 추가하고, tenant 비교가 있는
엔드포인트(execute 등)는 fixture의 proposal/diagnosis `tenant_id`를 오버라이드한 org와 일치시킨다.
실패 메시지를 읽고 원인 확인 후 수정(흔한 수정 추정 금지).

- [ ] **Step 3: Ruff 전체 통과 확인**

Run: `cd backend && uv run ruff format . && uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 4: 최종 커밋(수정분 있으면)**

```bash
git add backend/tests/management/
git commit -m "fix: 인증 추가로 영향받은 기존 매니지먼트 라우터 테스트 보정"
```

---

## 완료 기준 (스펙 §7 대응)

1. 13개 엔드포인트 전부 미인증 호출 시 401. ✅ Task 3·4·5·6·7 인증 테스트
2. DB 적재 캠페인 cross-tenant delete/activate/pause/sync 403. ✅ Task 5
3. `/execute` cross-tenant 제안 실행 403. ✅ Task 3
4. `/sync`가 쿼리 `org_id`를 신뢰하지 않음. ✅ Task 5 (쿼리 파라미터 제거)
5. 기존 mock 데모 흐름·테스트 무회귀. ✅ Task 9
6. Vuln 2 핸드오프 문서 커밋. ✅ Task 8

**미해결/후속(스펙 대비 편차):**
- `/budget/limit` per-org 키 전환 — GET /budget 동시 수정 필요(Task 6 편차 노트).
- 프론트 `lib/api.ts` Authorization 헤더 첨부 점검 — 프론트 범위, 별도 작업.
- `/sync` GET→POST 메서드 변경 — 프론트 호출부 영향, 후속.
