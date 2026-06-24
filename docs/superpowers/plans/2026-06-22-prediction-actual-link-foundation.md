# 예측↔실측 연결 토대 (C안) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 캠페인과 시뮬을 잇는 연결 키(`CreatedCampaign.simulation_id`)를 영속화하고 `SimPredictionReader`를 실구현·배선해, 성과비교 탭의 "집행 전(시뮬 예측)"이 실측 옆에 자동으로 붙게 한다.

**Architecture:** management 도메인은 simulation 도메인을 import하지 않고 **raw SQL**로만 시뮬 테이블을 읽는다(import-linter 경계). 예측은 포트(`PredictionReader`)+어댑터(`SimPredictionReader`)로 분리돼 wiring 한 곳에서 교체된다. 쓰기는 수동 create-proposal(형제 키)과 이미 구현된 from-simulation(snapshot 키) 두 경로를 `_record_created_campaign`이 함께 영속한다.

**Tech Stack:** Python · FastAPI · SQLAlchemy 2.0(async) · Alembic · pytest(asyncio_mode=auto) · Pydantic v2.

**근거 spec:** `docs/superpowers/specs/2026-06-22-prediction-actual-link-foundation-design.md`

> **조율 선행(착수 전):** `core/models.py` 변경은 공유 DB라 사전 공지 + Alembic + 양측 리뷰 대상(루트·management CLAUDE.md). Task 1 머지 전 🅰와 합의. `comparison/` 변경 범위도 사전 확인.

---

## File Structure

| 파일 | 작업 | 책임 |
|---|---|---|
| `backend/core/models.py` | 수정 | `CreatedCampaign.simulation_id` 컬럼(🤝 공유) |
| `backend/alembic/versions/020_created_campaign_simulation_id.py` | 생성 | 마이그레이션 |
| `backend/domain/management/comparison/ports.py` | 수정 | `PredictionReader.get_prediction` 시그니처 |
| `backend/domain/management/comparison/prediction_adapters.py` | 수정 | Mock 시그니처 + `SimPredictionReader` 실구현 |
| `backend/domain/management/wiring.py` | 수정 | `build_prediction_reader` Mock→Sim |
| `backend/api/routers/management.py` | 수정 | `_record_created_campaign` 영속 · `CreateCampaignRequest`/`create_campaign_proposal` 쓰기·org검증 · `compare_before_after` 매핑 |
| `backend/domain/management/assistant/tools.py` | 수정 | `live_before_after` 매핑 |
| `backend/tests/management/test_sim_prediction_reader.py` | 생성 | reader 단위 |
| `backend/tests/management/test_record_created_campaign.py` | 생성 | 영속 단위 |
| `backend/tests/management/test_create_proposal_router.py` | 수정 | 쓰기 경로·org검증 |
| `backend/tests/management/test_before_after_mapping.py` | 생성 | 라우터·tools 매핑 |

---

## Task 1: `CreatedCampaign.simulation_id` 컬럼 + 마이그레이션

**Files:**
- Modify: `backend/core/models.py:592-593` (CreatedCampaign, creative_ad_id 다음 줄)
- Create: `backend/alembic/versions/020_created_campaign_simulation_id.py`
- Test: `backend/tests/management/test_record_created_campaign.py` (Task 5에서 확장, 여기선 컬럼 존재만)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_record_created_campaign.py` 신규:
```python
# CreatedCampaign.simulation_id 컬럼 존재 + _record_created_campaign 영속 단위
from core.models import CreatedCampaign


def test_created_campaign_has_simulation_id_column():
    cols = CreatedCampaign.__table__.columns
    assert "simulation_id" in cols
    assert cols["simulation_id"].nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_record_created_campaign.py -v`
Expected: FAIL — `AssertionError` ("simulation_id" not in columns)

- [ ] **Step 3: Add the column**

`backend/core/models.py` — `creative_ad_id` 줄(593) 바로 아래에 추가:
```python
    # 집행 전 시뮬 예측 연결용 — 이 캠페인이 어떤 시뮬 런(simulations.id)으로 집행됐는지(없으면 미연결).
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
```
(`uuid`·`UUID`·`Mapped`·`mapped_column`은 이미 import됨 — 추가 import 불요.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_record_created_campaign.py -v`
Expected: PASS

- [ ] **Step 5: Write the Alembic migration**

`backend/alembic/versions/020_created_campaign_simulation_id.py` 신규:
```python
"""add created_campaigns.simulation_id — 집행 전 시뮬 예측 연결용

Revision ID: 020
Revises: 019
Create Date: 2026-06-22

캠페인이 어떤 시뮬 런(simulations.id)으로 집행됐는지 저장해, 예측(전)↔실측(후) 비교에서
정확히 매칭한다. creative_ad_id(Meta 재사용)와 별도 컬럼. 기존 행은 NULL(시뮬 미연결).
"""

from alembic import op

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE created_campaigns ADD COLUMN IF NOT EXISTS simulation_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE created_campaigns DROP COLUMN IF EXISTS simulation_id")
```

- [ ] **Step 6: Commit** (DB 적용 `alembic upgrade head`는 🤝 공유 DB라 양측 합의 후 별도 실행)

```bash
cd /c/Users/804-0/click_me
git add backend/core/models.py backend/alembic/versions/020_created_campaign_simulation_id.py backend/tests/management/test_record_created_campaign.py
git commit -m "add: created_campaigns.simulation_id 컬럼 + 마이그레이션(예측↔실측 연결 키)"
```

---

## Task 2: 포트·Mock 시그니처 전환 (`get_prediction(simulation_id, tenant_id)`)

**Files:**
- Modify: `backend/domain/management/comparison/ports.py:18-25`
- Modify: `backend/domain/management/comparison/prediction_adapters.py:23-45` (MockPredictionReader)
- Test: `backend/tests/management/test_sim_prediction_reader.py` (Mock 부분)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_sim_prediction_reader.py` 신규(Mock 케이스 먼저):
```python
# SimPredictionReader 단위 + Mock 시그니처
import uuid

from domain.management.comparison.prediction_adapters import MockPredictionReader

_ORG = str(uuid.uuid4())
_SIM = str(uuid.uuid4())


async def test_mock_reader_new_signature_returns_snapshot():
    snap = await MockPredictionReader().get_prediction(_SIM, _ORG)
    assert snap is not None
    assert snap.source == "mock"
    assert 0.0 <= snap.click_intent_rate <= 1.0


async def test_mock_reader_empty_key_none():
    assert await MockPredictionReader().get_prediction("", _ORG) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_sim_prediction_reader.py -v`
Expected: FAIL — `TypeError` (get_prediction() takes 2 positional args but 3 were given)

- [ ] **Step 3: Update the port signature**

`backend/domain/management/comparison/ports.py` — `PredictionReader` 교체:
```python
class PredictionReader(Protocol):
    """집행 전 시뮬 예측 읽기 — 시뮬 디커플링 슬롯.

    simulation_id로 해당 시뮬 런의 예측을 읽는다. tenant_id로 org 대조(타 org 노출 차단).
    예측이 없거나 org 불일치면 None(시뮬 미연결).
    """

    async def get_prediction(
        self, simulation_id: str, tenant_id: str
    ) -> PredictionSnapshot | None: ...
```

- [ ] **Step 4: Update the Mock signature**

`backend/domain/management/comparison/prediction_adapters.py` — `MockPredictionReader.get_prediction`의 `self, ad_id: str` 를 `self, simulation_id: str, tenant_id: str` 로 바꾸고, 본문에서 `ad_id` 사용을 `simulation_id`로 치환(seed 계산·`PredictionSnapshot(ad_id=simulation_id, ...)`). `tenant_id`는 사용하지 않음(해시 기반 mock):
```python
    async def get_prediction(
        self, simulation_id: str, tenant_id: str
    ) -> PredictionSnapshot | None:
        if not simulation_id:
            return None
        seed = sum(ord(c) for c in simulation_id)
        click_intent = round(0.35 + (seed % 50) / 100, 3)  # 0.35~0.84
        purchase = round(2.5 + (seed % 25) / 10, 1)  # 2.5~4.9
        trust = round(2.8 + (seed % 20) / 10, 1)  # 2.8~4.7
        rejection = round((seed % 30) / 100, 3)  # 0.00~0.29
        score = 40 + (seed % 55)  # 40~94
        return PredictionSnapshot(
            ad_id=simulation_id,
            click_intent_rate=min(click_intent, 1.0),
            purchase_intent=min(purchase, 5.0),
            trust_avg=min(trust, 5.0),
            rejection_rate=min(rejection, 1.0),
            objective_fit_score=score,
            grade=_grade(score),
            as_of=datetime.now(UTC),
            source="mock",
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_sim_prediction_reader.py -v`
Expected: PASS (2 mock 테스트)

- [ ] **Step 6: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/domain/management/comparison/ports.py backend/domain/management/comparison/prediction_adapters.py backend/tests/management/test_sim_prediction_reader.py
git commit -m "edit: PredictionReader 조회 키를 simulation_id+tenant_id로 전환(Mock 포함)"
```

---

## Task 3: `SimPredictionReader` 실구현 (raw SQL + org 대조)

**Files:**
- Modify: `backend/domain/management/comparison/prediction_adapters.py:48-56` (SimPredictionReader)
- Test: `backend/tests/management/test_sim_prediction_reader.py` (Sim 케이스 추가)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_sim_prediction_reader.py` 에 추가:
```python
from domain.management.comparison.prediction_adapters import SimPredictionReader

_AD = str(uuid.uuid4())


class _Row:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt, params=None):
        return _Row(self._row)


def _factory(row):
    # (ad_id, organization_id, completed_at, cir, purchase_intent_avg, trust_avg, rejection_rate)
    def make():
        return _FakeSession(row)

    return make


async def test_sim_reader_maps_aggregate():
    row = (_AD, _ORG, None, 0.42, 3.8, 4.1, 0.12)
    snap = await SimPredictionReader(_factory(row)).get_prediction(_SIM, _ORG)
    assert snap is not None
    assert snap.source == "sim"
    assert snap.ad_id == _AD
    assert snap.click_intent_rate == 0.42
    assert snap.purchase_intent == 3.8
    assert snap.trust_avg == 4.1
    assert snap.rejection_rate == 0.12
    assert snap.objective_fit_score is None


async def test_sim_reader_other_org_none():
    row = (_AD, str(uuid.uuid4()), None, 0.42, 3.8, 4.1, 0.12)
    assert await SimPredictionReader(_factory(row)).get_prediction(_SIM, _ORG) is None


async def test_sim_reader_no_row_none():
    assert await SimPredictionReader(_factory(None)).get_prediction(_SIM, _ORG) is None


async def test_sim_reader_bad_uuid_none():
    assert await SimPredictionReader(_factory(None)).get_prediction("not-a-uuid", _ORG) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_sim_prediction_reader.py -v`
Expected: FAIL — `test_sim_reader_maps_aggregate` 등에서 `SimPredictionReader(...)` 가 `__init__` 인자를 안 받음/`None` 반환

- [ ] **Step 3: Implement SimPredictionReader**

`backend/domain/management/comparison/prediction_adapters.py` — 파일 상단 import에 추가:
```python
import uuid

from sqlalchemy import text
```
`SimPredictionReader` 클래스를 교체:
```python
class SimPredictionReader:
    """실 시뮬 예측 읽기 — simulation_id로 simulation_aggregates를 raw SQL 조회(도메인 경계).

    org 불일치/미완료(aggregate 없음)/미존재/형식오류는 None(연결 대기). simulation 도메인
    ORM import 금지 — 테이블·컬럼명 문자열로만 접근. as_of는 시뮬 완료시각(UTC aware).
    """

    _SQL = text(
        """
        SELECT s.ad_id, s.organization_id, s.completed_at,
               a.click_intent_rate, a.purchase_intent_avg, a.trust_avg, a.rejection_rate
        FROM simulations s
        JOIN simulation_aggregates a ON a.simulation_id = s.id
        WHERE s.id = :sid
        """
    )

    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def get_prediction(
        self, simulation_id: str, tenant_id: str
    ) -> PredictionSnapshot | None:
        try:
            sid = uuid.UUID(str(simulation_id))
        except (ValueError, TypeError):
            return None
        async with self._session_factory() as db:
            row = (await db.execute(self._SQL, {"sid": str(sid)})).first()
        if row is None:
            return None
        if str(row[1]) != str(tenant_id):  # org 대조
            return None
        as_of = row[2].replace(tzinfo=UTC) if row[2] is not None else datetime.now(UTC)
        return PredictionSnapshot(
            ad_id=str(row[0]),
            click_intent_rate=float(row[3]),
            purchase_intent=float(row[4]),
            trust_avg=float(row[5]),
            rejection_rate=float(row[6]),
            objective_fit_score=None,  # 시뮬 파생값 — 다음 단계
            grade=None,
            as_of=as_of,
            source="sim",
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_sim_prediction_reader.py -v`
Expected: PASS (mock 2 + sim 4 = 6 통과)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/domain/management/comparison/prediction_adapters.py backend/tests/management/test_sim_prediction_reader.py
git commit -m "add: SimPredictionReader 실구현(raw SQL + org 대조)"
```

---

## Task 4: wiring 교체 (Mock → Sim, 세션 팩토리 주입)

**Files:**
- Modify: `backend/domain/management/wiring.py:84-94`
- Test: `backend/tests/management/test_comparison_wiring.py` (추가)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_comparison_wiring.py` 에 추가(파일 끝):
```python
def test_build_prediction_reader_is_sim():
    from types import SimpleNamespace

    from domain.management.comparison.prediction_adapters import SimPredictionReader
    from domain.management.wiring import build_prediction_reader

    reader = build_prediction_reader(SimpleNamespace(use_mock=True))
    assert isinstance(reader, SimPredictionReader)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_comparison_wiring.py::test_build_prediction_reader_is_sim -v`
Expected: FAIL — `MockPredictionReader` 인스턴스라 `isinstance(... SimPredictionReader)` False

- [ ] **Step 3: Swap wiring to Sim**

`backend/domain/management/wiring.py` — `build_prediction_reader` 교체:
```python
def build_prediction_reader(settings):
    """집행 전(시뮬 예측) reader — simulation_aggregates를 raw SQL로 읽는 SimPredictionReader.

    실데이터가 있으면 실 예측, 없으면 None(연결 대기). 데모/단위 테스트는 MockPredictionReader를
    직접 주입해 사용(가짜 예측 합성은 테스트 전용 — 운영은 합성 금지).
    """
    from core.db import AsyncSessionLocal  # noqa: PLC0415
    from domain.management.comparison.prediction_adapters import (  # noqa: PLC0415
        SimPredictionReader,
    )

    return SimPredictionReader(AsyncSessionLocal)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_comparison_wiring.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/domain/management/wiring.py backend/tests/management/test_comparison_wiring.py
git commit -m "edit: build_prediction_reader를 SimPredictionReader로 교체(세션 팩토리 주입)"
```

---

## Task 5: `_record_created_campaign` 두 키 영속

**Files:**
- Modify: `backend/api/routers/management.py:301-318` (`_record_created_campaign`)
- Test: `backend/tests/management/test_record_created_campaign.py` (확장)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_record_created_campaign.py` 에 추가:
```python
import uuid
from types import SimpleNamespace

import pytest

from api.routers import management

_SIM = str(uuid.uuid4())
_SIM2 = str(uuid.uuid4())


class _CaptureDB:
    def __init__(self):
        self.added = None

    def add(self, obj):
        self.added = obj

    async def commit(self):
        return None


def _proposal(evidence):
    return SimpleNamespace(
        evidence_metrics=evidence,
        tenant_id="org_1",
        ad_account_id="act_1",
        budget_after_krw=10000,
    )


def _result():
    return SimpleNamespace(status=SimpleNamespace(value="success"), platform_response_snapshot={})


@pytest.mark.parametrize(
    "evidence,expected",
    [
        ({"campaign_config": {"name": "C"}, "simulation_id": _SIM}, _SIM),
        ({"campaign_config": {"name": "C"}, "simulation_snapshot": {"simulation_id": _SIM2}}, _SIM2),
        ({"campaign_config": {"name": "C"}, "simulation_id": _SIM,
          "simulation_snapshot": {"simulation_id": _SIM2}}, _SIM),  # 수동 우선
        ({"campaign_config": {"name": "C"}}, None),
    ],
)
async def test_record_persists_simulation_id(evidence, expected):
    db = _CaptureDB()
    await management._record_created_campaign(db, _proposal(evidence), _result())
    got = db.added.simulation_id
    assert (str(got) if got else None) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_record_created_campaign.py -k persists -v`
Expected: FAIL — `CreatedCampaign`에 `simulation_id`가 안 실려 `db.added.simulation_id` 가 항상 None (또는 AttributeError 없음이나 값 불일치)

- [ ] **Step 3: Update `_record_created_campaign`**

`backend/api/routers/management.py` — `_record_created_campaign` 본문을 교체(시그니처 동일):
```python
async def _record_created_campaign(db: AsyncSession, proposal: ActionProposal, result) -> None:
    """캠페인 생성 결과를 created_campaigns에 누적 기록 — 실패해도 응답엔 영향 없음(best-effort)."""
    cfg = proposal.evidence_metrics.get("campaign_config") or {}
    meta_id = _find_in_snapshot(result.platform_response_snapshot, "campaign_meta_id")
    em = proposal.evidence_metrics
    # 두 경로 — 수동 create-proposal 형제 키(우선) + from-simulation snapshot 키.
    raw_sim = em.get("simulation_id") or (em.get("simulation_snapshot") or {}).get("simulation_id")
    sim_uuid = None
    if raw_sim:
        try:
            sim_uuid = UUID(str(raw_sim))
        except (ValueError, TypeError):
            sim_uuid = None
    db.add(
        CreatedCampaign(
            tenant_id=proposal.tenant_id,
            meta_campaign_id=str(meta_id) if meta_id else None,
            name=cfg.get("name") or proposal.evidence_metrics.get("name") or "(이름없음)",
            objective=cfg.get("objective", "traffic"),
            ad_account_id=proposal.ad_account_id,
            daily_budget_krw=int(cfg.get("daily_budget_krw") or proposal.budget_after_krw or 0),
            status=result.status.value if hasattr(result.status, "value") else str(result.status),
            execution_mode=str(_resolved_execution_mode().value),
            creative_ad_id=cfg.get("creative_ad_id"),  # Meta 기존 광고 재사용 귀속
            simulation_id=sim_uuid,  # 시뮬 예측 연결 키(수동 + from-simulation)
        )
    )
    await db.commit()
```
(`UUID`는 `from uuid import UUID, uuid4`로 이미 import됨.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_record_created_campaign.py -v`
Expected: PASS (컬럼 존재 1 + 영속 4 파라미터)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/api/routers/management.py backend/tests/management/test_record_created_campaign.py
git commit -m "add: _record_created_campaign이 simulation_id 영속(수동+from-simulation 두 키)"
```

---

## Task 6: create-proposal 쓰기 경로 + 쓰기 시점 org 검증

**Files:**
- Modify: `backend/api/routers/management.py:965-972` (`CreateCampaignRequest`)
- Modify: `backend/api/routers/management.py:1027-1089` (`create_campaign_proposal`)
- Test: `backend/tests/management/test_create_proposal_router.py` (추가)

- [ ] **Step 1: Write the failing test**

먼저 기존 테스트 구조 확인: `cd backend && uv run pytest tests/management/test_create_proposal_router.py -v` 로 현재 통과 픽스처(`get_db`/`get_current_user` 오버라이드, body 헬퍼)를 파악한 뒤, 같은 픽스처를 재사용해 아래를 추가한다. 테스트는 `simulations` org 검증용 `db.scalar`가 필요하므로, 그 파일의 fake db가 `scalar`에서 `organization_members`(org_id)와 `from simulations`(소유 1/None)를 분기 반환하도록 보강한다.

`backend/tests/management/test_create_proposal_router.py` 에 추가(파일의 기존 `_client`/`_body` 헬퍼 재사용; 없으면 test_from_simulation.py 패턴을 그대로 차용):
```python
import uuid

_SIM = "22222222-2222-2222-2222-222222222222"


def test_create_proposal_carries_simulation_id(client_with_sim):
    # client_with_sim: simulations org 검증 통과(소유) 픽스처
    resp = client_with_sim.post(
        "/api/management/campaigns/create-proposal",
        json=_proposal_body(simulation_id=_SIM),
    )
    assert resp.status_code == 200, resp.text
    em = resp.json()["proposal"]["evidence_metrics"]
    assert em["simulation_id"] == _SIM


def test_create_proposal_bad_simulation_uuid_422(client_with_sim):
    resp = client_with_sim.post(
        "/api/management/campaigns/create-proposal",
        json=_proposal_body(simulation_id="not-a-uuid"),
    )
    assert resp.status_code == 422


def test_create_proposal_other_org_simulation_422(client_without_sim):
    # client_without_sim: from simulations 소유 조회가 None(미존재/타 org)
    resp = client_without_sim.post(
        "/api/management/campaigns/create-proposal",
        json=_proposal_body(simulation_id=_SIM),
    )
    assert resp.status_code == 422
```

> `_proposal_body(**over)` 는 기존 create-proposal 테스트의 정상 body(name·objective·daily_budget_krw·run_days·country·age·gender 등)에 `simulation_id`를 끼우는 헬퍼. `client_with_sim`/`client_without_sim` 은 fake db의 `scalar`가 `from simulations` 조회에서 각각 `1`/`None` 을 돌려주도록 구성한 TestClient 픽스처(test_from_simulation.py의 `_FakeDB`·`dependency_overrides` 패턴 차용).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_create_proposal_router.py -k simulation -v`
Expected: FAIL — `simulation_id` 필드 미지(`extra` 무시되거나 422 아님) / evidence_metrics에 키 없음

- [ ] **Step 3: Add request field**

`backend/api/routers/management.py` — `CreateCampaignRequest` 에 필드 추가(`creative_ad_id` 근처):
```python
    simulation_id: str | None = None  # 이 캠페인이 연결될 시뮬 런(UUID). 없으면 예측 미연결.
```

- [ ] **Step 4: Add write-time validation + evidence key**

`backend/api/routers/management.py` — `create_campaign_proposal` 안, `config = CampaignConfig(...)` 조립 **이전**에 검증 블록 추가:
```python
    # 시뮬 연결 키 — 형식·org 소유 검증(방어 심층, 읽기 시점 대조와 이중).
    if body.simulation_id is not None:
        try:
            sid = UUID(body.simulation_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="simulation_id 형식 오류") from exc
        owned = await db.scalar(
            text("SELECT 1 FROM simulations WHERE id = :sid AND organization_id = :org"),
            {"sid": str(sid), "org": str(org_id)},
        )
        if not owned:
            raise HTTPException(
                status_code=422, detail="해당 시뮬을 찾을 수 없거나 권한이 없습니다."
            )
```
그리고 `evidence_metrics` dict 에 키 추가:
```python
            evidence_metrics={
                "campaign_config": config.model_dump(mode="json"),
                "name": body.name,
                "simulation_id": body.simulation_id,
            },
```
`text` import 확인 — 파일 상단에 `from sqlalchemy import text` 가 없으면 추가(기존 raw SQL 사용처가 있으면 이미 있음).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_create_proposal_router.py -v`
Expected: PASS (기존 + 신규 3)

- [ ] **Step 6: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/api/routers/management.py backend/tests/management/test_create_proposal_router.py
git commit -m "add: create-proposal optional simulation_id 수신·org검증·evidence 영속"
```

---

## Task 7: before-after 라우터 매핑 (creative 유지 + sim 추가)

**Files:**
- Modify: `backend/api/routers/management.py:466-500` (`compare_before_after`)
- Test: `backend/tests/management/test_before_after_mapping.py` (생성)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_before_after_mapping.py` 신규:
```python
# before-after — creative_ad_id는 실측 귀속 유지, simulation_id는 예측 키로 전달되는지
import uuid
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.db import get_db

_SIM = uuid.uuid4()


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):
        return _Result(self._rows)


def test_before_after_passes_sim_and_keeps_creative(monkeypatch):
    calls = {}

    class _Pred:
        async def get_prediction(self, simulation_id, tenant_id):
            calls["pred"] = (simulation_id, tenant_id)
            return None

    class _Reader:
        async def list_campaigns(self):
            return [SimpleNamespace(campaign_id="m1", name="C1")]

        async def get_metrics(self, cid, now):
            return object()

    def fake_real_outcome(m, cid, creative_id):
        calls["creative"] = creative_id
        return SimpleNamespace()

    def fake_cba(cid, name, prediction, actual):
        calls["prediction_arg"] = prediction
        return SimpleNamespace(model_dump=lambda mode=None: {"campaign_id": cid, "name": name})

    monkeypatch.setattr(management, "build_reader", lambda s: _Reader())
    monkeypatch.setattr(management, "build_prediction_reader", lambda s: _Pred())
    monkeypatch.setattr(management, "_real_outcome", fake_real_outcome)
    monkeypatch.setattr(management, "compute_before_after", fake_cba)

    rows = [
        SimpleNamespace(
            meta_campaign_id="m1", creative_ad_id="cr1", simulation_id=_SIM, tenant_id="org_1"
        )
    ]
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_db] = lambda: _FakeDB(rows)
    res = TestClient(app).get("/api/management/compare/before-after")

    assert res.status_code == 200, res.text
    assert calls["pred"] == (str(_SIM), "org_1")  # 예측 키 = simulation_id + tenant
    assert calls["creative"] == "cr1"  # 실측 귀속 = creative_ad_id 유지
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_before_after_mapping.py -v`
Expected: FAIL — 현재 매핑이 `creative_ad_id`만 만들어 `get_prediction`을 (creative_ad_id) 1-인자로 호출 → `calls["pred"]` 불일치/TypeError

- [ ] **Step 3: Update the mapping**

`backend/api/routers/management.py` — `compare_before_after` 내부의 `ad_by_meta` 빌드 블록(466-480 부근)을 두 맵으로 교체:
```python
    # meta_campaign_id → creative_ad_id(실측 귀속) / (simulation_id, tenant_id)(예측 키)
    creative_by_meta: dict[str, str] = {}
    sim_by_meta: dict[str, tuple[str, str]] = {}
    try:
        rows = (
            (await db.execute(select(CreatedCampaign).where(CreatedCampaign.deleted_at.is_(None))))
            .scalars()
            .all()
        )
        for r in rows:
            if not r.meta_campaign_id:
                continue
            if r.creative_ad_id:
                creative_by_meta[str(r.meta_campaign_id)] = r.creative_ad_id
            if r.simulation_id:
                sim_by_meta[str(r.meta_campaign_id)] = (str(r.simulation_id), r.tenant_id)
    except Exception:  # noqa: BLE001 — 매핑 실패해도 실측은 보여준다
        creative_by_meta = {}
        sim_by_meta = {}
```
그리고 루프 내부(491-499 부근)를 교체:
```python
    for c in campaigns:
        cid = c.campaign_id
        try:
            actual = _real_outcome(
                await reader.get_metrics(cid, now), cid, creative_by_meta.get(cid)
            )
        except Exception:  # noqa: BLE001 — 캠페인 1건 실측 실패가 전체를 막지 않게
            continue
        link = sim_by_meta.get(cid)
        prediction = await pred_reader.get_prediction(link[0], link[1]) if link else None
        ba = compute_before_after(cid, c.name, prediction, actual)
        items.append(ba.model_dump(mode="json"))
    return {"items": items}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_before_after_mapping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/api/routers/management.py backend/tests/management/test_before_after_mapping.py
git commit -m "edit: before-after 매핑 — creative 귀속 유지 + simulation_id 예측 키 추가"
```

---

## Task 8: assistant tools `live_before_after` 매핑

**Files:**
- Modify: `backend/domain/management/assistant/tools.py:112-139` (`live_before_after`)
- Test: `backend/tests/management/test_before_after_mapping.py` (추가)

- [ ] **Step 1: Write the failing test**

`backend/tests/management/test_before_after_mapping.py` 에 추가:
```python
async def test_tools_live_before_after_passes_sim(monkeypatch):
    from contextlib import asynccontextmanager

    from domain.management.assistant import tools

    calls = {}

    class _Pred:
        async def get_prediction(self, simulation_id, tenant_id):
            calls["pred"] = (simulation_id, tenant_id)
            return None

    class _Reader:
        async def list_campaigns(self):
            return [SimpleNamespace(campaign_id="m1", name="C1")]

        async def get_metrics(self, cid, now):
            return object()

    rows = [
        SimpleNamespace(
            meta_campaign_id="m1", creative_ad_id="cr1", simulation_id=_SIM, tenant_id="org_1"
        )
    ]

    @asynccontextmanager
    async def fake_session():
        yield _FakeDB(rows)

    monkeypatch.setattr(tools, "AsyncSessionLocal", fake_session)
    monkeypatch.setattr(tools, "build_reader", lambda s: _Reader())
    monkeypatch.setattr(tools, "build_prediction_reader", lambda s: _Pred())
    monkeypatch.setattr(tools, "_outcome", lambda m, cid, creative_id: calls.setdefault("creative", creative_id) or SimpleNamespace())
    monkeypatch.setattr(
        tools,
        "compute_before_after",
        lambda cid, name, prediction, actual: SimpleNamespace(
            name=name, verdict=SimpleNamespace(value="unknown"), rationale="r"
        ),
    )

    out = await tools.live_before_after(SimpleNamespace())
    assert out["items"][0]["name"] == "C1"
    assert calls["pred"] == (str(_SIM), "org_1")
    assert calls["creative"] == "cr1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && uv run pytest tests/management/test_before_after_mapping.py -k tools -v`
Expected: FAIL — 현재 `ad_by_meta`가 creative_ad_id 1-값이라 `get_prediction` 호출 시그니처 불일치

- [ ] **Step 3: Update `live_before_after`**

`backend/domain/management/assistant/tools.py` — `live_before_after` 의 `ad_by_meta` 빌드 + 루프를 교체:
```python
    creative_by_meta: dict[str, str] = {}
    sim_by_meta: dict[str, tuple[str, str]] = {}
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(CreatedCampaign).where(CreatedCampaign.deleted_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                if not r.meta_campaign_id:
                    continue
                if r.creative_ad_id:
                    creative_by_meta[str(r.meta_campaign_id)] = r.creative_ad_id
                if r.simulation_id:
                    sim_by_meta[str(r.meta_campaign_id)] = (str(r.simulation_id), r.tenant_id)
    except Exception:  # noqa: BLE001 — 매핑 실패해도 실측은 보여준다
        creative_by_meta = {}
        sim_by_meta = {}
    try:
        items = []
        for c in await reader.list_campaigns():
            cid = c.campaign_id
            m = await reader.get_metrics(cid, now)
            link = sim_by_meta.get(cid)
            prediction = await pred.get_prediction(link[0], link[1]) if link else None
            ba = compute_before_after(cid, c.name, prediction, _outcome(m, cid, creative_by_meta.get(cid)))
            items.append({"name": ba.name, "verdict": ba.verdict.value, "rationale": ba.rationale})
        return {"items": items}
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && uv run pytest tests/management/test_before_after_mapping.py -v`
Expected: PASS (라우터 1 + tools 1)

- [ ] **Step 5: Commit**

```bash
cd /c/Users/804-0/click_me
git add backend/domain/management/assistant/tools.py backend/tests/management/test_before_after_mapping.py
git commit -m "edit: assistant live_before_after 매핑 — creative 유지 + simulation_id 예측 키"
```

---

## Task 9: 전구간 회귀 + Ruff

**Files:** 없음(검증만)

- [ ] **Step 1: Ruff 정렬·린트**

Run: `cd backend && uv run ruff format . && uv run ruff check . --fix`
Expected: 변경 파일 정렬, 린트 통과(또는 자동수정).

- [ ] **Step 2: 변경 도메인 테스트**

Run: `cd backend && uv run pytest tests/management/ -q`
Expected: PASS(신규 포함). 특히 회귀 — `test_from_simulation.py`, `test_compare_router.py`, `test_create_proposal_router.py` 그린.

- [ ] **Step 3: 전구간 회귀**

Run: `cd backend && uv run pytest tests/ -q`
Expected: PASS(전체 그린).

- [ ] **Step 4: Ruff 잔여 변경 커밋(있으면)**

```bash
cd /c/Users/804-0/click_me
git add -A backend
git commit -m "fix: Ruff 포맷·린트 정렬(예측↔실측 토대)"
```

---

## 완료 후

- **DB 적용** — `alembic upgrade head`(020)는 공유 Neon DB라 🅰 합의 후 적용. 적용 전엔 `CreatedCampaign.simulation_id` 쓰기가 실DB에서 실패할 수 있으니 머지 순서 조율.
- **다음 단계(이연)** — 수동 캠페인 폼의 "내 시뮬 이력 선택" 드롭다운 + 시뮬 이력 조회 API, `objective_fit_score`/`grade` 실값, before-after 엔드포인트 org 인증.

---

## Self-Review (작성자 점검 완료)

- **Spec 커버리지** — §4 컬럼(T1)·§5 reader(T3)·§6 포트/호출부(T2·T7·T8)·§7 쓰기 두 키(T5)+create-proposal(T6)·§8 에러(T6 422·reader None)·§9 테스트(각 Task)·§3 wiring(T4). 전부 매핑됨.
- **플레이스홀더** — 없음(모든 코드·명령·기대결과 명시). T6의 픽스처는 기존 파일 재사용을 명시하고 패턴 출처(test_from_simulation.py) 지정.
- **타입 일관성** — `get_prediction(simulation_id, tenant_id)` 시그니처가 ports·Mock·Sim·라우터·tools 호출부에서 일치. `simulation_id` 컬럼은 `UUID(as_uuid=True)`, 영속 시 `UUID(str(...))` 변환 일관. `creative_by_meta`/`sim_by_meta` 명명 라우터·tools 동일.
