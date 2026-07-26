# management 이중 배선 정리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 실행 확정 롱텀 기록(history_recorder)을 라우터 executor에 배선하고(CREATE_CAMPAIGN 역추적 분기 포함), 실행 모드 해석·state version을 wiring 정본으로 통합한 뒤, 죽은 챗 집행 브릿지 `build_executor`를 제거한다.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-12-management-wiring-dedup-design.md`의 3커밋 시퀀스(fix → edit → delete). 각 커밋은 독립적으로 green. 커밋 2가 wiring 함수의 새 소비자(라우터)를 만든 뒤 커밋 3이 옛 소비자(build_executor)를 지우므로 중간 어느 시점에도 고아 함수가 없다.

**Tech Stack:** FastAPI 라우터 + 순수 Python DI(wiring), pytest(asyncio 자동 모드, monkeypatch 캡처 — DB 없이 hermetic), Ruff.

**공통 명령** — 테스트: `cd backend && uv run pytest ../test/backend/management/ -v` / 린트: `cd backend && uv run ruff format . && uv run ruff check . --fix`

**주의:** `test/backend/management/helpers.py`의 테스트 헬퍼 `build_executor`는 이번에 삭제하는 `domain/management/wiring.py`의 `build_executor`와 동명이인이다. 헬퍼는 절대 건드리지 않는다.

---

### Task 0: 설계·계획 문서 커밋

**Files:**
- 신규(이미 작성됨): `docs/superpowers/specs/2026-07-12-management-wiring-dedup-design.md`
- 신규(이 파일): `docs/superpowers/plans/2026-07-12-management-wiring-dedup.md`

- [ ] **Step 1: 커밋**

```bash
git add docs/superpowers/specs/2026-07-12-management-wiring-dedup-design.md docs/superpowers/plans/2026-07-12-management-wiring-dedup.md
git commit -m "add: management 이중 배선 정리 설계·구현 계획 문서"
```

---

### Task 1: history_link 콜백 계약 테스트 (커밋 1의 실패 테스트)

**Files:**
- Test 생성: `test/backend/management/test_history_link.py`

CREATE 제안은 생성 경로별로 귀속 단서가 다르다 — 수동 폼=`campaign_config.creative_ad_id`(management.py:2320 부근), 시뮬 기반=`simulation_snapshot.source_ad_id`(:2842), 후보 기반=`candidate_snapshot.generation_id`(:2481). 셋 다 커버하는 우선순위 체인(creative_ad_id → source_ad_id → generation_id)을 계약으로 고정한다(계획 리뷰 P1).

신규 resolver 2종은 아직 없으므로 `raising=False`로 patch한다 — **기존 경로 테스트 4건은 처음부터 통과**하고(기준선 유지, 계획 리뷰 P3), **CREATE 계열 4건만 의미 있는 assertion으로 실패**해야 정상이다.

- [ ] **Step 1: 테스트 파일 작성**

```python
# history_link 콜백 계약 — payload·actor 매핑·미귀속 생략·CREATE_CAMPAIGN 분기 고정
"""record_execution·resolve 함수를 monkeypatch로 캡처해 DB 없이 계약을 고정한다.

executor가 콜백을 '언제' 부르는지는 test_history_recorder.py 소관 — 여기는 콜백이
불렸을 때 '무엇을' 기록하는지만 본다.
"""

from uuid import uuid4

from management.helpers import NOW, make_action, make_proposal

import domain.management.history_link as hl
from domain.management.contracts.enums import ResultStatus
from domain.management.contracts.schemas import AUTO_APPROVER, ActionResult
from domain.management.history_link import build_history_recorder


def _result(status: ResultStatus = ResultStatus.SUCCESS) -> ActionResult:
    return ActionResult(
        result_id=str(uuid4()),
        approval_id="",
        idempotency_key="k",
        status=status,
        executed_at=NOW,
    )


def _capture(monkeypatch, *, ids_result="proj-ids", ad_result=None, gen_result=None):
    """resolve 3종·record_execution을 패치하고 캡처 dict를 돌려준다.

    fake resolver는 실물처럼 '입력이 없으면 None'을 지켜 체인 폴백이 테스트에서도 동작한다.
    raising=False — 신규 resolver 2종이 아직 없어도 기존 경로 테스트는 통과(기준선 유지).
    """
    captured: dict = {"records": [], "resolve_ids": None, "resolve_ad": [], "resolve_gen": []}

    async def _resolve(ids):
        captured["resolve_ids"] = list(ids)
        return ids_result

    async def _resolve_ad(ad_id):
        captured["resolve_ad"].append(ad_id)
        return ad_result if ad_id else None

    async def _resolve_gen(generation_id):
        captured["resolve_gen"].append(generation_id)
        return gen_result if generation_id else None

    async def _record(pid, feature_type, action, summary, payload=None, user_id=None):
        captured["records"].append(
            {
                "project_id": pid,
                "feature_type": feature_type,
                "action": action,
                "summary": summary,
                "payload": payload,
            }
        )

    monkeypatch.setattr(hl, "resolve_project_id", _resolve)
    monkeypatch.setattr(hl, "resolve_project_id_from_ad", _resolve_ad, raising=False)
    monkeypatch.setattr(hl, "resolve_project_id_from_generation", _resolve_gen, raising=False)
    monkeypatch.setattr(hl, "record_execution", _record)
    return captured


async def test_records_contract_fields(monkeypatch):
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal()  # PAUSE_CAMPAIGN, target=("camp-001",)
    action = make_action(proposal)  # approver_id="user-77"

    await record(action, proposal, _result())

    assert len(captured["records"]) == 1
    rec = captured["records"][0]
    assert rec["project_id"] == "proj-ids"
    assert rec["feature_type"] == "management"
    assert rec["action"] == "pause_campaign"  # action_type 소문자화
    assert "일시중지" in rec["summary"] and "camp-001" in rec["summary"]
    assert rec["payload"]["actor"] == "user"
    assert rec["payload"]["status"] == ResultStatus.SUCCESS.value


async def test_auto_approver_maps_to_actor_auto(monkeypatch):
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal()
    action = make_action(proposal, approver_id=AUTO_APPROVER)

    await record(action, proposal, _result())

    assert captured["records"][0]["payload"]["actor"] == "auto"


async def test_skips_when_project_unresolved(monkeypatch):
    captured = _capture(monkeypatch, ids_result=None)
    record = build_history_recorder()
    proposal = make_proposal()

    await record(make_action(proposal), proposal, _result())

    assert captured["records"] == []


async def test_non_create_uses_target_ids_resolver(monkeypatch):
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal()

    await record(make_action(proposal), proposal, _result())

    assert captured["resolve_ids"] == ["camp-001"]
    assert captured["resolve_ad"] == []  # CREATE 전용 경로 미사용
    assert captured["resolve_gen"] == []


async def test_create_manual_resolves_via_creative_ad_id(monkeypatch):
    # CREATE의 target_object_ids는 광고계정 id(옵션 A)·created_campaigns는 미적재 시점 —
    # 수동 폼 제안은 campaign_config.creative_ad_id가 유일한 귀속 단서(스펙 리뷰 P1).
    captured = _capture(monkeypatch, ad_result="proj-a")
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={"campaign_config": {"creative_ad_id": "ad-uuid-1"}},
    )

    await record(make_action(proposal), proposal, _result())

    assert captured["resolve_ad"][0] == "ad-uuid-1"
    assert captured["resolve_ids"] is None  # 계정 id로 캠페인 역추적 시도 금지
    assert captured["records"][0]["action"] == "create_campaign"
    assert captured["records"][0]["project_id"] == "proj-a"


async def test_create_simulation_falls_back_to_source_ad_id(monkeypatch):
    # 시뮬 기반 제안(management.py:2842)은 creative_ad_id 없이 simulation_snapshot만 가짐.
    captured = _capture(monkeypatch, ad_result="proj-s")
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={
            "campaign_config": {},
            "simulation_snapshot": {"source_ad_id": "ad-uuid-2"},
        },
    )

    await record(make_action(proposal), proposal, _result())

    # 체인: creative_ad_id(None)→source_ad_id 순으로 같은 resolver가 두 번 불린다.
    assert captured["resolve_ad"] == [None, "ad-uuid-2"]
    assert captured["records"][0]["project_id"] == "proj-s"


async def test_create_candidate_falls_back_to_generation_id(monkeypatch):
    # 후보 기반 제안(management.py:2481)은 candidate_snapshot.generation_id만 가짐 —
    # AdGeneration.project_id(core/models.py:546)로 귀속.
    captured = _capture(monkeypatch, gen_result="proj-g")
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={
            "campaign_config": {},
            "candidate_snapshot": {"generation_id": "gen-uuid-1"},
        },
    )

    await record(make_action(proposal), proposal, _result())

    assert captured["resolve_gen"] == ["gen-uuid-1"]
    assert captured["records"][0]["project_id"] == "proj-g"


async def test_create_without_any_clue_skips(monkeypatch):
    # 모든 귀속 단서(creative_ad_id·source_ad_id·generation_id) 부재 → 기록 생략.
    captured = _capture(monkeypatch)
    record = build_history_recorder()
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        target_object_ids=("act_001",),
        evidence_metrics={"campaign_config": {}},
    )

    await record(make_action(proposal), proposal, _result())

    assert captured["records"] == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_history_link.py -v`
Expected: 기존 경로 4건(`contract_fields`·`auto_approver`·`skips_when_unresolved`·`non_create`) **PASS**, CREATE 계열 4건 **FAIL** — 현재 구현은 CREATE도 `resolve_project_id(target_object_ids)`로 가므로 `resolve_ad`/`resolve_gen` 캡처가 비어 있고 project_id가 "proj-ids"로 잘못 귀속되는, 의미 있는 assertion 실패여야 한다(AttributeError가 아님 — `raising=False` 덕).

---

### Task 2: history_link에 CREATE_CAMPAIGN 분기 구현

**Files:**
- Modify: `backend/domain/management/history_link.py`

- [ ] **Step 1: resolver 2종 추가 + 콜백 분기**

상단 import(17행) 교체 — `AdGeneration` 추가:

```python
from core.models import Ad, AdGeneration, CreatedCampaign
```

`resolve_project_id` 함수(46~67행) 바로 아래에 추가:

```python
async def resolve_project_id_from_ad(ad_id: str | None) -> str | None:
    """광고 UUID → ads.project_id (best-effort) — created_campaigns 미적재 시점용.

    CREATE_CAMPAIGN은 target_object_ids가 광고계정 id고, recorder 호출 시점엔
    created_campaigns row도 아직 없어(적재가 execute 이후) 캠페인 역추적이 불가능하다.
    제안에 실린 광고 UUID(creative_ad_id 또는 source_ad_id)로 ads를 직조회한다.
    """
    aid = _maybe_uuid(ad_id or "")
    if aid is None:
        return None
    try:
        async with AsyncSessionLocal() as db:
            ad = await db.get(Ad, aid)
            if ad is not None:
                return str(ad.project_id)
    except Exception as exc:  # noqa: BLE001 — 역추적 실패면 기록 생략
        print(f"[management] project resolve error: {exc!r}")
    return None


async def resolve_project_id_from_generation(generation_id: str | None) -> str | None:
    """생성 요청 UUID → ad_generations.project_id (best-effort) — 후보 기반 CREATE 귀속용."""
    gid = _maybe_uuid(generation_id or "")
    if gid is None:
        return None
    try:
        async with AsyncSessionLocal() as db:
            gen = await db.get(AdGeneration, gid)
            if gen is not None and gen.project_id is not None:
                return str(gen.project_id)
    except Exception as exc:  # noqa: BLE001 — 역추적 실패면 기록 생략
        print(f"[management] project resolve error: {exc!r}")
    return None
```

`build_history_recorder` 내부 `record()`의 첫 줄(`project_id = await resolve_project_id(...)`)을 분기로 교체:

```python
    async def record(
        action: ApprovedAction, proposal: ActionProposal, result: ActionResult
    ) -> None:
        if proposal.action_type == "CREATE_CAMPAIGN":
            # 생성 경로별 귀속 단서 우선순위 — 수동 폼(creative_ad_id) →
            # 시뮬 기반(simulation_snapshot.source_ad_id) →
            # 후보 기반(candidate_snapshot.generation_id → AdGeneration.project_id).
            ev = proposal.evidence_metrics or {}
            cfg = ev.get("campaign_config") or {}
            sim = ev.get("simulation_snapshot") or {}
            cand = ev.get("candidate_snapshot") or {}
            project_id = (
                await resolve_project_id_from_ad(cfg.get("creative_ad_id"))
                or await resolve_project_id_from_ad(sim.get("source_ad_id"))
                or await resolve_project_id_from_generation(cand.get("generation_id"))
            )
        else:
            project_id = await resolve_project_id(proposal.target_object_ids)
        if project_id is None:
            return
```

이후 로직(actor·label·summary·record_execution 호출)은 무변경.

- [ ] **Step 2: 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_history_link.py -v`
Expected: 8건 전부 PASS

---

### Task 3: 라우터 executor 배선 + 배선·도달 테스트

**Files:**
- Modify: `backend/api/routers/management.py` (import 1줄 + `_get_executor` 2곳)
- Test 생성: `test/backend/management/test_executor_wiring.py`

- [ ] **Step 1: 배선·도달 테스트 작성**

```python
# _get_executor 배선 검증 — history_recorder 부착(전역·org)·데모 격리·record_execution 도달
"""부착 여부(hermetic)와 승인 발행→execute()→record_execution 도달(통합형)을 고정한다.

콜백이 '무엇을' 기록하는지는 test_history_link.py, executor가 '언제' 부르는지는
test_history_recorder.py 소관 — 여기는 라우터 배선이 끝까지 이어지는지만 본다.
"""

from datetime import UTC, datetime, timedelta

import pytest
from management.helpers import FakeWriter, make_action, make_proposal

from api.routers import management as m

import domain.management.history_link as hl
from domain.management.contracts.approval_ledger import record_from_action
from domain.management.contracts.enums import ActionTier, ResultStatus
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.contracts.schemas import CampaignConfig


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch):
    """모듈 전역 executor 캐시 초기화 + mock 고정(다른 테스트와 격리)."""
    monkeypatch.setattr(m.settings, "use_mock", True, raising=False)
    m._executor = None
    m._demo_executor_instance = None
    yield
    m._executor = None
    m._demo_executor_instance = None


def test_global_executor_has_history_recorder():
    assert m._get_executor()._history_recorder is not None


def test_org_scoped_executor_has_history_recorder():
    assert m._get_executor(FakeWriter())._history_recorder is not None


def test_demo_executor_has_no_history_recorder():
    # 시연 격리 — 데모 경로는 DB(chat_execution_history)를 건드리지 않는다.
    assert m._demo_executor()._history_recorder is None


async def test_execute_reaches_record_execution(monkeypatch):
    """승인 발행→_get_executor().execute() 성공 시 record_execution까지 도달(스펙 리뷰 P2).

    recorder가 붙어 있어도 기록이 생략되는 회귀(CREATE 역추적 공백류)를 잡는 게 목적 —
    resolve만 fake고 나머지는 실경로(원장 게이트 포함)를 그대로 탄다.
    """
    calls: list[str] = []

    async def _resolve(ids):
        return "proj-1"

    async def _record(pid, feature_type, action, summary, payload=None, user_id=None):
        calls.append(action)

    monkeypatch.setattr(hl, "resolve_project_id", _resolve)
    monkeypatch.setattr(hl, "record_execution", _record)

    now = datetime.now(UTC)
    # 라우터 executor 게이트 정합값 — state_v1(라우터 provider)·실 정책 버전·미만료 시각.
    proposal = make_proposal(
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )
    action = make_action(
        proposal,
        approval_policy_version=APPROVAL_POLICY_VERSION,
        approved_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    await m._APPROVAL_STORE.put(record_from_action(action))  # 원장 발행(게이트 #5)

    result = await m._get_executor(FakeWriter()).execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert calls == ["pause_campaign"]


async def test_execute_create_campaign_reaches_record_execution(monkeypatch):
    """CREATE 제안 실물 형태(campaign_config + snapshot)가 실경로에서 기록까지 도달(계획 리뷰 P2).

    시뮬 기반 형태(source_ad_id 귀속)로 executor CREATE 디스패치(evidence의 campaign_config →
    CampaignConfig → create_full_campaign, executor.py:680)를 그대로 태운다 — PAUSE 도달
    테스트만으로는 CREATE 역추적 공백 회귀를 못 잡는다.
    """
    calls: list[str] = []

    async def _resolve_ad(ad_id):
        return "proj-1" if ad_id else None

    async def _record(pid, feature_type, action, summary, payload=None, user_id=None):
        calls.append(action)

    monkeypatch.setattr(hl, "resolve_project_id_from_ad", _resolve_ad)
    monkeypatch.setattr(hl, "record_execution", _record)

    now = datetime.now(UTC)
    config = CampaignConfig(
        campaign_id="camp_sim_wiring1",
        tenant_id="org-1111",
        ad_account_id="act_001",
        name="시뮬 기반 캠페인",
        objective="traffic",
        daily_budget_krw=50_000,
        start_at=now,
        end_at=now + timedelta(days=7),
    )
    proposal = make_proposal(
        action_type="CREATE_CAMPAIGN",
        action_tier=ActionTier.TIER_3,
        target_object_ids=("act_001",),  # 옵션 A — CREATE 대상은 광고계정
        evidence_metrics={
            "campaign_config": config.model_dump(mode="json"),
            "simulation_snapshot": {"source_ad_id": "11111111-1111-1111-1111-111111111111"},
        },
        budget_before_krw=0,
        budget_after_krw=50_000,
        max_total_spend_krw=350_000,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        metrics_as_of=now,
        expires_at=now + timedelta(hours=1),
    )
    action = make_action(  # TIER_3은 make_action이 proposal에서 tier 승계, approver는 사람
        proposal,
        approval_policy_version=APPROVAL_POLICY_VERSION,
        approved_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    await m._APPROVAL_STORE.put(record_from_action(action))

    result = await m._get_executor(FakeWriter()).execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert calls == ["create_campaign"]
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_executor_wiring.py -v`
Expected: 배선 2건 FAIL(`_history_recorder is None` — 전역·org), 데모 1건 PASS, 도달 2건(PAUSE·CREATE) FAIL(`calls == []`)

- [ ] **Step 3: 라우터 배선 추가**

`backend/api/routers/management.py` — wiring import 블록(134~143행)은 그대로 두고, 그 위 도메인 import들 사이(알파벳 순서상 `from domain.management.escalation_demo import ...` 다음, 118행 부근)에 추가:

```python
from domain.management.history_link import build_history_recorder
```

`_get_executor()`의 두 `Executor(...)` 생성부에 각각 한 줄 추가 (org writer 분기 280행 부근·전역 싱글턴 분기 291행 부근, `approvals=_APPROVAL_STORE,` 앞):

```python
            history_recorder=build_history_recorder(),  # 실행 확정 → 롱텀 메모리 기록
```

`_demo_executor()`는 무변경.

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_executor_wiring.py ../test/backend/management/test_history_link.py ../test/backend/management/test_history_recorder.py -v`
Expected: 전부 PASS

- [ ] **Step 5: management 스위트 전체 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/management/ -v`
Expected: 전부 PASS (recorder 추가로 기존 라우터 테스트가 깨지면 안 됨 — 콜백은 best-effort·suppress라 실행 결과 불변)

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/history_link.py backend/api/routers/management.py test/backend/management/test_history_link.py test/backend/management/test_executor_wiring.py
git commit -m "fix: 실행 확정 롱텀 기록 배선 — _get_executor에 history_recorder 부착 + CREATE_CAMPAIGN creative_ad_id 역추적 분기"
```

---

### Task 4: 실행 모드·state version wiring 정본 통합 (커밋 2)

**Files:**
- Modify: `backend/api/routers/management.py`
- Modify: `backend/domain/management/wiring.py` (docstring만)

행동 불변 리팩토링 — 신규 테스트 없음, 기존 `test_live_mode_gate.py` 4케이스가 래퍼 경유로 wiring 정본을 검증한다(스펙 리뷰 P3).

- [ ] **Step 1: 라우터를 wiring 정본으로 전환**

`backend/api/routers/management.py`

wiring import 블록(134~143행)에 두 항목 추가(알파벳 순):

```python
from domain.management.wiring import (
    build_approval_store,
    build_audit_sink,
    build_escalation_store,
    build_generator_client,
    build_idempotency_store,
    build_prediction_reader,
    build_reader,
    build_writer,
    resolve_execution_mode,
    state_version_v1,
)
```

contracts.policy import 블록(87~97행)에 `DEFAULT_MONTHLY_TARGET_KRW` 추가:

```python
from domain.management.contracts.policy import (
    APPROVAL_POLICY_VERSION,
    BASE_CTR,
    CPM_ANCHOR_KRW,
    CPM_NORMAL_RANGE_KRW,
    DAILY_BUDGET_KRW,
    DEFAULT_MONTHLY_TARGET_KRW,
    FATIGUE_FREQUENCY,
    PROPOSAL_TTL_MINUTES,
    exec_gate_thresholds,
    is_executable_verdict,
)
```

`_BUDGET`(186행) 리터럴을 상수로:

```python
_BUDGET = TenantBudgetRegistry(default_limit_krw=DEFAULT_MONTHLY_TARGET_KRW)
```

`_state_version`(244~245행) 함수 삭제, executor 생성부 3곳(`_get_executor` 두 분기·`_demo_executor`)의 `state_version_provider=_state_version` → `state_version_provider=state_version_v1`.

`_resolved_execution_mode`(248~260행) 본문을 위임으로 교체:

```python
def _resolved_execution_mode() -> ExecutionMode:
    """실행 모드 — 정본은 wiring.resolve_execution_mode(use_mock이면 MOCK 봉인).

    LIVE 분기는 /approve와 사용자 명시 실행 엔드포인트(활성화·중지·예산 변경 등)에서
    이 함수로 판정한다(AUTO 자율 승인은 안 거침).
    """
    return resolve_execution_mode(settings)
```

`backend/domain/management/wiring.py` — `resolve_execution_mode` docstring 첫 줄 교체:

```python
def resolve_execution_mode(settings):
    """settings 기반 실행 모드 정본 — 라우터 _resolved_execution_mode가 이 함수에 위임.

    use_mock이면 무조건 MOCK(봉인). 실모드에서만 management_execution_mode를 따른다.
    DRY_RUN을 폴백으로 사용한다.
    """
```

- [ ] **Step 2: 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/management/ -v`
Expected: 전부 PASS — 특히 `test_live_mode_gate.py` 4건(래퍼가 이제 wiring을 경유하지만 `m.settings` monkeypatch가 같은 settings 객체를 패치하므로 그대로 유효)

- [ ] **Step 3: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py backend/domain/management/wiring.py
git commit -m "edit: 실행 모드 해석·state version wiring 정본 통합 + 예산 캡 policy 상수화"
```

---

### Task 5: 죽은 챗 집행 브릿지 build_executor 삭제 (커밋 3)

**Files:**
- Modify: `backend/domain/management/wiring.py`

- [ ] **Step 1: 삭제 전 호출자 0 재확인**

Run: `rg -n "wiring import build_executor|wiring\.build_executor" backend test; if ($LASTEXITCODE -ne 0) { "no callers" }` (저장소 루트, PowerShell — 계획 실행자가 Grep 도구를 쓸 수 있으면 같은 패턴으로 대체 가능)
Expected: `no callers` — 패턴을 wiring 한정으로 좁힌 이유: `\bbuild_executor\b`로 넓히면 test/backend/management/helpers.py의 동명 테스트 헬퍼 사용처 30여 곳이 오탐으로 걸린다.

- [ ] **Step 2: 삭제 및 주석 갱신**

`backend/domain/management/wiring.py`

- 섹션 주석(187행) 교체: `# ── 챗 오케스트레이터 공유 팩토리 (라우터와 병렬, 통합은 추후) ───────────────────────────` → `# ── 실행 모드·state version 정본 — 라우터 _resolved_execution_mode·executor 조립이 사용 ──────`
- `build_executor` 함수 전체(212~252행, `def build_executor` 부터 파일 끝의 `return Executor(...)` 닫힘까지) 삭제. 함수 내부 지연 import(`ExecutionMode`·`policy 상수`·`Executor`·`TenantBudgetRegistry`·`build_history_recorder`)는 함수와 함께 사라짐 — wiring 상단 import에는 원래 없었으므로 추가 정리 불필요.
- `resolve_execution_mode`·`state_version_v1`·나머지 build_* 함수는 존치.

- [ ] **Step 3: 전체 회귀 + import 무결성 확인**

Run: `cd backend && uv run pytest ../test/backend/management/ -v && uv run python -c "import domain.management.wiring"`
Expected: 테스트 전부 PASS, import 에러 없음

- [ ] **Step 4: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/wiring.py
git commit -m "delete: 죽은 챗 집행 브릿지 build_executor 제거 — 소비자는 26-06-29 병합에서 소멸, 정본 함수만 존치"
```

---

### Task 6: 전체 스위트 최종 확인

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && uv run pytest ../test/backend/ -v`
Expected: 전부 PASS (chat·generator 스위트 포함 — history_link 시그니처 변화가 없어 영향 없음)

- [ ] **Step 2: 스펙 후속 과제 확인**

스펙의 "범위 밖 / 후속 과제" 2건(구 오케스트레이터 데드코드 발표 후 삭제, org live 분기 wiring 우회 정리)은 이번 구현에 포함하지 않았음을 재확인 — 코드에 임시 TODO를 남기지 않는다.
