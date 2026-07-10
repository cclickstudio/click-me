# 리밸런스(transfer) 실집행 연결 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 예산 리밸런싱(캠페인 간 이전) 제안을 승인 1건·원자 액션 1건(REBALANCE_BUDGET)으로 Meta 실집행까지 연결한다 — 보상(원복) 포함, 챗 카드·스케줄러 알림·프론트 1-call 교체까지.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-11-rebalance-transfer-execution-design.md` 기준. executor `_call_targets` 초입에서 `REBALANCE_BUDGET`을 전용 함수 `_call_rebalance`로 분기(타깃 순회 밖) — 감액→증액→실패 시 보상 1회. 라우터는 `POST /budget/rebalance-commit`(budget-commit 골격 재사용). 챗은 `apply_rebalance` 툴 → `rebalance_action` 위젯 카드(카드 클릭 = 승인). 단일 adjust는 기존 budget-commit 유지.

**Tech Stack:** FastAPI + pydantic(계약), pytest(uv), Next.js/TS(pnpm), LangChain @tool.

**공통 규칙**
- 백엔드 .py 수정 태스크는 커밋 전 `cd backend && uv run ruff format . && uv run ruff check . --fix` 실행.
- 커밋 컨벤션 `타입: 한국어 설명` (add/edit/fix). 새 .py/.tsx 파일 첫 줄에 한국어 헤더 주석.
- 테스트 실행: `cd backend && uv run pytest ../test/backend/management/<파일> -v` (경로가 안 잡히면 `uv run pytest ../test -k <키워드> -v`).

---

### Task 1: 계약·정책 — REBALANCE_BUDGET 지원 등록 + Tier 2 게이트 완화

**Files:**
- Modify: `backend/domain/management/execution/executor.py:46-55` (SUPPORTED_ACTION_TYPES), `:317-318` (_validate Tier 2)
- Modify: `backend/domain/management/contracts/policy.py:22` (주석)
- Test: `test/backend/management/test_rebalance_execution.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성** — 신규 파일 `test/backend/management/test_rebalance_execution.py` 생성. 이 파일의 헬퍼(fake writer·제안·executor 빌더)는 Task 2 테스트도 같이 쓴다.

```python
# 리밸런스(REBALANCE_BUDGET) 원자 집행 — 전용 경로·보상·멱등·Tier2 게이트 검증
"""executor._call_rebalance의 감액→증액→보상 시퀀스와 실패 시맨틱을 검증한다."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.approval import issue_approval
from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    ResultStatus,
)
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.contracts.schemas import (
    ActionProposal,
    ActionResult,
    finalize_proposal,
)
from domain.management.execution.approval_stores import InMemoryApprovalStore
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import (
    AUTO_APPROVER,
    Executor,
    InMemoryIdempotencyStore,
)
from domain.management.execution.tier import BudgetAuthority


class FakeRebalanceWriter:
    """adjust_budget만 구현한 fake — 파생 멱등키 suffix(dec|inc|comp)로 실패를 주입한다."""

    def __init__(self, fail: set[str] | None = None):
        self.calls: list[tuple[str, int, str]] = []
        self.fail = fail or set()

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        self.calls.append((campaign_id, amount_krw, idem_key))
        leg = idem_key.rsplit(":", 1)[-1]
        failed = leg in self.fail
        return ActionResult(
            result_id=uuid4().hex,
            approval_id="",
            status=ResultStatus.FAILED if failed else ResultStatus.SUCCESS,
            failure_reason=FailureReason.PLATFORM_ERROR if failed else None,
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
        )


async def _state_v1(_ad_account_id: str) -> str:
    return "state_v1"


def make_rebalance_proposal(**overrides) -> ActionProposal:
    now = datetime.now(UTC)
    base = dict(
        proposal_id=f"prop_{uuid4().hex[:8]}",
        tenant_id="tenant-1",
        ad_account_id="act_1",
        target_object_ids=("camp_from", "camp_to"),
        action_type="REBALANCE_BUDGET",
        action_tier=ActionTier.TIER_2,
        evidence_metrics={
            "from_before_krw": 50_000,
            "from_after_krw": 40_000,
            "to_before_krw": 30_000,
            "to_after_krw": 40_000,
            "move_krw": 10_000,
        },
        metrics_as_of=now,
        hypothesis="테스트 리밸런스",
        confidence=1.0,
        expected_state_version="state_v1",
        budget_before_krw=80_000,
        budget_after_krw=80_000,
        max_total_spend_krw=0,
        expires_at=now + timedelta(minutes=10),
        approval_policy_version=APPROVAL_POLICY_VERSION,
    )
    base.update(overrides)
    return finalize_proposal(ActionProposal(**base))


def build_rebalance_executor(writer, approvals) -> Executor:
    return Executor(
        writer,
        idempotency=InMemoryIdempotencyStore(),
        audit=InMemoryAuditLog(),
        budget_for=lambda _tenant: BudgetAuthority(limit_krw=10_000_000),
        state_version_provider=_state_v1,
        current_policy_version=APPROVAL_POLICY_VERSION,
        approvals=approvals,
    )


async def _approved(proposal, approver="user-1", store=None):
    store = store or InMemoryApprovalStore()
    action = await issue_approval(
        proposal, approver, execution_mode=ExecutionMode.MOCK, store=store
    )
    return action, store


# ── Task 1: Tier 2 게이트 ─────────────────────────────────────────


async def test_tier2_user_approval_passes_gate():
    """사용자 승인 TIER_2는 INVALID_TIER로 거부되지 않는다."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal, approver="user-1")
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.failure_reason is not FailureReason.INVALID_TIER
    assert result.failure_reason is not FailureReason.UNSUPPORTED_ACTION


async def test_tier2_auto_approver_blocked():
    """AUTO 승인 TIER_2는 INVALID_TIER로 거부(자율 실행 비활성 유지)."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal, approver=AUTO_APPROVER)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.REJECTED
    assert result.failure_reason is FailureReason.INVALID_TIER
    assert writer.calls == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_execution.py -v`
Expected: `test_tier2_user_approval_passes_gate` FAIL — 현재는 `UNSUPPORTED_ACTION` 또는 `INVALID_TIER`로 거부됨. `test_tier2_auto_approver_blocked`는 PASS일 수 있음(현행도 차단이므로) — 첫 테스트 실패만 확인하면 됨.

- [ ] **Step 3: 구현** — `backend/domain/management/execution/executor.py`

46-55줄 `SUPPORTED_ACTION_TYPES` 튜플에 한 줄 추가.

```python
    "CHANGE_BID_STRATEGY",  # 에스컬레이션 사다리 2순위 — 입찰 전략 변경 (direct)
    "REBALANCE_BUDGET",  # Tier 2 — 캠페인 간 일예산 이전(총액 불변), 전용 경로 _call_rebalance
)
```

317-318줄의 무조건 차단을 Tier 3 게이트(319줄)와 같은 패턴으로 교체.

```python
# 변경 전
        if action.action_tier is ActionTier.TIER_2:
            return FailureReason.INVALID_TIER, "Tier 2 자동 실행은 v1 비활성"
# 변경 후
        if action.action_tier is ActionTier.TIER_2 and action.approver_id == AUTO_APPROVER:
            return FailureReason.INVALID_TIER, "Tier 2는 건별 사용자 승인 필수 (자율 실행 비활성)"
```

`backend/domain/management/contracts/policy.py:22` 주석 갱신.

```python
    "REBALANCE_BUDGET": ActionTier.TIER_2,  # 총액 불변 이전 — 건별 사용자 승인(자율 실행 비활성)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_execution.py -v`
Expected: 2개 PASS. 주의 — 이 시점에 `test_tier2_user_approval_passes_gate`는 `_call_targets`가 타깃 2개를 순회하며 `_dispatch`의 `ValueError("미지원 action_type")`를 만나 PLATFORM_ERROR로 끝나지만, 단언은 INVALID_TIER/UNSUPPORTED_ACTION 아님만 보므로 통과한다(전용 경로는 Task 2).

- [ ] **Step 5: 기존 executor 테스트 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_execution_units.py -v`
Expected: 전부 PASS. Tier 2 무조건 차단을 단언하는 기존 테스트가 있으면 실패한다 — 그 경우 해당 테스트를 "AUTO 승인 차단" 단언으로 갱신(사용자 승인 통과가 새 정본).

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/execution/executor.py backend/domain/management/contracts/policy.py test/backend/management/test_rebalance_execution.py
git commit -m "add: REBALANCE_BUDGET 액션 등록 + Tier2 사용자 승인 허용 (AUTO는 차단 유지)"
```

---

### Task 2: executor — `_call_rebalance` 전용 실행 경로 (감액→증액→보상)

**Files:**
- Modify: `backend/domain/management/execution/executor.py` — `_call_targets`(342줄) 초입 분기, `_call_with_retry`(395줄) call 파라미터, `_call_rebalance` 신규
- Test: `test/backend/management/test_rebalance_execution.py` (Task 1 파일에 추가)

- [ ] **Step 1: 실패하는 테스트 작성** — Task 1 파일 하단에 추가.

```python
# ── Task 2: _call_rebalance 시퀀스 ────────────────────────────────


async def test_rebalance_success_two_legs_in_order():
    """감액(from)→증액(to) 순서로 각 1회, 파생 멱등키(dec/inc) 사용."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.SUCCESS
    assert [(c[0], c[1]) for c in writer.calls] == [("camp_from", 40_000), ("camp_to", 40_000)]
    assert writer.calls[0][2].endswith(":camp_from:dec")
    assert writer.calls[1][2].endswith(":camp_to:inc")


async def test_rebalance_first_leg_failure_releases_idempotency():
    """감액 실패 = 아무것도 집행 안 됨 — 비-PARTIAL 실패, 멱등키 해제로 재시도 가능."""
    writer = FakeRebalanceWriter(fail={"dec"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PLATFORM_ERROR
    assert len(writer.calls) == 1  # 감액 1회만, 증액·보상 없음

    retry = await executor.execute(action, proposal)  # 멱등키 해제 → 재실행 가능
    assert len(writer.calls) == 2  # replay가 아니라 실제 재호출
    assert retry.status is ResultStatus.FAILED


async def test_rebalance_compensation_success_is_retryable():
    """증액 실패 + 보상 성공 = 원복 완료 — 비-PARTIAL 실패 + compensation=succeeded."""
    writer = FakeRebalanceWriter(fail={"inc"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PLATFORM_ERROR  # PARTIAL 아님
    calls = [(c[0], c[1]) for c in writer.calls]
    assert calls == [("camp_from", 40_000), ("camp_to", 40_000), ("camp_from", 50_000)]
    assert writer.calls[2][2].endswith(":camp_from:comp")
    snaps = (result.platform_response_snapshot or {}).get("targets") or []
    assert any(s.get("compensation") == "succeeded" for s in snaps)


async def test_rebalance_compensation_failure_is_sealed():
    """증액·보상 모두 실패 = 부분 변경 방치 — PARTIAL_FAILURE 박제, 같은 승인 재집행 차단."""
    writer = FakeRebalanceWriter(fail={"inc", "comp"})
    proposal = make_rebalance_proposal()
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)
    assert result.status is ResultStatus.FAILED
    assert result.failure_reason is FailureReason.PARTIAL_FAILURE
    snaps = (result.platform_response_snapshot or {}).get("targets") or []
    assert any(s.get("compensation") == "failed" for s in snaps)

    calls_before = len(writer.calls)
    replayed = await executor.execute(action, proposal)  # 박제 결과 재생, writer 미호출
    assert replayed.failure_reason is FailureReason.PARTIAL_FAILURE
    assert len(writer.calls) == calls_before


async def test_rebalance_missing_evidence_fails_without_calls():
    """evidence_metrics 필드 누락은 writer 호출 전 실패(계약 방어)."""
    writer = FakeRebalanceWriter()
    proposal = make_rebalance_proposal(evidence_metrics={"move_krw": 10_000})
    action, store = await _approved(proposal)
    executor = build_rebalance_executor(writer, store)

    result = await executor.execute(action, proposal)

    assert result.status is ResultStatus.FAILED
    assert writer.calls == []
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_execution.py -v -k rebalance`
Expected: Task 2 테스트 5개 FAIL (현재는 타깃 순회 → `_dispatch` ValueError 경로라 호출 순서·보상·스냅샷이 없음).

- [ ] **Step 3: 구현** — `backend/domain/management/execution/executor.py`

3-a. `_call_targets`(342줄) 초입에 분기 추가.

```python
    async def _call_targets(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        key: str,
    ) -> ActionResult:
        # REBALANCE_BUDGET은 타깃 순회로 처리하면 from/to 각각에서 리밸런스가 반복된다
        # (액션 1건 = 두 다리 + 보상) — 전용 경로로 한 번만 처리한다.
        if proposal.action_type == "REBALANCE_BUDGET":
            return await self._call_rebalance(run, action, proposal, key)
        snapshots: list[dict[str, Any]] = []
        ...  # 이하 기존 코드 무변경
```

3-b. `_call_with_retry`(395줄)에 선택 파라미터 `call` 추가 — 기존 호출부 무변경, 리밸런스 다리가 amount를 클로저로 넘길 수 있게.

```python
    async def _call_with_retry(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        target: str,
        idem_key: str,
        call: Callable[[], Awaitable[ActionResult]] | None = None,
    ) -> ActionResult:
        timeout_attempts = 0
        rate_attempts = 0
        while True:
            run.record_attempt()
            try:
                outcome = await (
                    call() if call is not None else self._dispatch(proposal, target, idem_key)
                )
            except TimeoutError:
                ...  # 이하 기존 코드 무변경
```

3-c. `_call_rebalance` 신규 — `_call_targets` 아래에 추가.

```python
    async def _call_rebalance(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        key: str,
    ) -> ActionResult:
        """REBALANCE_BUDGET 전용 — 감액(from)→증액(to), 증액 실패 시 감액 원복(보상) 1회.

        총예산이 순간적으로도 늘지 않게 감액이 먼저다. 보상 성공=순변경 0(비-PARTIAL,
        멱등 해제로 재승인 후 재시도 가능), 보상 실패=PARTIAL_FAILURE(박제 — P5/게이트 #7,
        같은 승인 재집행 차단 + 수동 복구 안내).
        """
        em = proposal.evidence_metrics
        from_id, to_id = proposal.target_object_ids[0], proposal.target_object_ids[-1]
        try:
            from_before = int(em["from_before_krw"])
            from_after = int(em["from_after_krw"])
            to_after = int(em["to_after_krw"])
        except (KeyError, TypeError, ValueError):
            run.advance(RunStatus.FAILED)
            return self._build_result(
                action,
                key,
                ResultStatus.FAILED,
                FailureReason.PLATFORM_ERROR,
                [{"error": "REBALANCE_BUDGET evidence_metrics 필드 누락/불량"}],
            )

        snapshots: list[dict[str, Any]] = []

        async def _leg(target: str, amount: int, suffix: str) -> ActionResult:
            leg_key = f"{key}:{target}:{suffix}"
            outcome = await self._call_with_retry(
                run,
                action,
                proposal,
                target,
                leg_key,
                call=lambda: self._writer.adjust_budget(target, amount, leg_key),
            )
            snapshots.append(
                {
                    "target": target,
                    "leg": suffix,
                    "status": str(outcome.status),
                    "failure_reason": outcome.failure_reason,
                    "response": outcome.platform_response_snapshot,
                }
            )
            return outcome

        dec = await _leg(from_id, from_after, "dec")
        if dec.status is ResultStatus.FAILED:
            # 아무것도 집행 안 됨 — execute()가 멱등키를 해제해 재시도 가능.
            run.advance(RunStatus.FAILED, snapshot=snapshots[-1])
            return self._build_result(
                action,
                key,
                ResultStatus.FAILED,
                dec.failure_reason or FailureReason.PLATFORM_ERROR,
                snapshots,
            )
        run.record_snapshot(snapshots[-1])

        inc = await _leg(to_id, to_after, "inc")
        if inc.status is not ResultStatus.FAILED:
            run.advance(RunStatus.SUCCEEDED)
            return self._build_result(action, key, ResultStatus.SUCCESS, None, snapshots)

        comp = await _leg(from_id, from_before, "comp")
        if comp.status is not ResultStatus.FAILED:
            # 원복 완료 — 순변경 0. 비-PARTIAL이라 멱등키가 해제돼 재승인 후 재시도 가능.
            snapshots.append({"compensation": "succeeded"})
            run.advance(RunStatus.FAILED, snapshot=snapshots[-1])
            await self._record(
                run,
                action,
                proposal,
                "executor.rebalance_compensated",
                {"from": from_id, "to": to_id, "restored_krw": from_before},
            )
            return self._build_result(
                action,
                key,
                ResultStatus.FAILED,
                inc.failure_reason or FailureReason.PLATFORM_ERROR,
                snapshots,
            )

        # 보상까지 실패 — 부분 변경 방치 상태. 박제(재집행 차단) + 수동 복구 안내.
        snapshots.append(
            {
                "compensation": "failed",
                "manual_restore_target": from_id,
                "manual_restore_krw": from_before,
            }
        )
        run.advance(RunStatus.HALTED, snapshot=snapshots[-1])
        await self._record(
            run,
            action,
            proposal,
            "executor.partial_failure",
            {"from": from_id, "to": to_id, "compensation": "failed", "snapshots": snapshots},
        )
        return self._build_result(
            action, key, ResultStatus.FAILED, FailureReason.PARTIAL_FAILURE, snapshots
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_execution.py -v`
Expected: 전체(Task 1 포함 7개) PASS.

- [ ] **Step 5: 기존 테스트 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend/management -v`
Expected: 전부 PASS (기존 `_call_with_retry` 호출부는 시그니처 뒤에 기본값 파라미터만 추가돼 무영향).

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/execution/executor.py test/backend/management/test_rebalance_execution.py
git commit -m "add: executor REBALANCE_BUDGET 전용 경로 — 감액→증액→보상, PARTIAL 박제"
```

---

### Task 3: 라우터 — `POST /budget/rebalance-commit`

**Files:**
- Modify: `backend/api/routers/management.py` — `_build_budget_proposal`(3429줄) 근처에 요청 모델·검증·빌더·엔드포인트 추가
- Test: `test/backend/management/test_rebalance_commit_router.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# /budget/rebalance-commit 라우터 — drift 409·이동량 검증·원자 제안 빌드 확인
"""양쪽 캠페인 drift와 이동량 정합을 검증하고 REBALANCE_BUDGET 제안 1건을 집행하는지 본다."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management
from core.auth import get_current_user
from core.db import get_db
from domain.management.contracts.enums import ResultStatus
from domain.management.contracts.schemas import ActionResult


class _FakeDB:
    def __init__(self, org_id):
        self._org_id = org_id

    async def scalar(self, stmt, *a, **k):
        if "organization_members" in str(stmt):
            return self._org_id
        return None


class _TwoCampaignReader:
    """list_campaigns 기반 _current_daily_budget 소스 — 예산을 테스트에서 조정."""

    def __init__(self):
        self.budgets = {"camp_low": 50_000, "camp_high": 30_000}

    async def list_campaigns(self, include_archived=False):
        return [
            SimpleNamespace(campaign_id=cid, daily_budget_krw=b)
            for cid, b in self.budgets.items()
        ]


_BODY = {
    "from_campaign_id": "camp_low",
    "to_campaign_id": "camp_high",
    "from_after_krw": 40_000,
    "to_after_krw": 40_000,
    "move_krw": 10_000,
    "shown_from_before_krw": 50_000,
    "shown_to_before_krw": 30_000,
}


@pytest.fixture()
def env(monkeypatch):
    org_id = uuid.uuid4()
    reader = _TwoCampaignReader()
    captured: dict = {}

    async def fake_require_reader(db, org):
        return reader

    async def fake_require_owned(db, org, campaign_id):
        return None

    async def fake_require_ad_account(db, org):
        return "act_test"

    async def fake_require_writer(db, org):
        return object()  # 실 writer 미사용 — executor 자체를 fake로 대체

    class _FakeExecutor:
        async def execute(self, action, proposal):
            captured["action"] = action
            captured["proposal"] = proposal
            return ActionResult(
                result_id="r1",
                approval_id=action.approval_id,
                status=ResultStatus.SUCCESS,
                executed_at=datetime.now(UTC),
                idempotency_key="k",
            )

    # use_mock=False — _current_daily_budget이 데모 고정값이 아닌 fake reader를 보게 한다.
    monkeypatch.setattr(management.settings, "use_mock", False, raising=False)
    monkeypatch.setattr(
        management.settings, "management_execution_mode", "dry_run", raising=False
    )
    monkeypatch.setattr(management, "_require_reader", fake_require_reader)
    monkeypatch.setattr(management, "_require_owned_campaign", fake_require_owned)
    monkeypatch.setattr(management, "_require_ad_account", fake_require_ad_account)
    monkeypatch.setattr(management, "_require_writer", fake_require_writer)
    monkeypatch.setattr(management, "_get_executor", lambda writer=None: _FakeExecutor())

    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[get_db] = lambda: _FakeDB(org_id)
    return TestClient(app, raise_server_exceptions=False), reader, captured


def test_rebalance_commit_builds_atomic_proposal(env):
    client, _reader, captured = env
    res = client.post("/api/management/budget/rebalance-commit", json=_BODY)
    assert res.status_code == 200
    prop = captured["proposal"]
    assert prop.action_type == "REBALANCE_BUDGET"
    assert prop.target_object_ids == ("camp_low", "camp_high")
    assert prop.max_total_spend_krw == 0
    assert prop.evidence_metrics["from_before_krw"] == 50_000
    assert prop.evidence_metrics["to_after_krw"] == 40_000


def test_rebalance_commit_rejects_drift(env):
    client, reader, captured = env
    reader.budgets["camp_low"] = 60_000  # 제안 이후 예산 변동
    res = client.post("/api/management/budget/rebalance-commit", json=_BODY)
    assert res.status_code == 409
    assert "proposal" not in captured  # executor 진입 전 차단


def test_rebalance_commit_rejects_move_mismatch(env):
    client, _reader, captured = env
    res = client.post(
        "/api/management/budget/rebalance-commit", json={**_BODY, "move_krw": 5_000}
    )
    assert res.status_code == 409
    assert "proposal" not in captured


def test_rebalance_commit_rejects_same_campaign(env):
    client, _reader, _captured = env
    res = client.post(
        "/api/management/budget/rebalance-commit",
        json={**_BODY, "to_campaign_id": "camp_low"},
    )
    assert res.status_code == 422
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_commit_router.py -v`
Expected: 404 Not Found (엔드포인트 없음)로 전부 FAIL.

- [ ] **Step 3: 구현** — `backend/api/routers/management.py`의 `budget_commit`(3541줄) 아래에 추가.

```python
class RebalanceCommitRequest(BaseModel):
    from_campaign_id: str
    to_campaign_id: str
    from_after_krw: int
    to_after_krw: int
    move_krw: int = Field(gt=0)
    shown_from_before_krw: int | None = None
    shown_to_before_krw: int | None = None


async def _validate_rebalance_change(
    reader: AdPlatformReader, body: RebalanceCommitRequest
) -> tuple[int, int]:
    """양쪽 현재값(서버 정본)으로 drift·이동량·범위를 검증하고 (from_before, to_before) 반환."""
    if body.from_campaign_id == body.to_campaign_id:
        raise HTTPException(422, "같은 캠페인끼리는 예산을 옮길 수 없어요.")
    from_before = await _current_daily_budget(reader, body.from_campaign_id)
    to_before = await _current_daily_budget(reader, body.to_campaign_id)
    if from_before <= 0 or to_before <= 0:
        raise HTTPException(409, "현재 일예산을 확인할 수 없어 리밸런싱을 진행할 수 없어요.")
    if body.shown_from_before_krw is not None and body.shown_from_before_krw != from_before:
        raise HTTPException(
            409, f"저효율 캠페인 예산이 {from_before:,}원으로 바뀌었어요. 제안을 다시 확인해 주세요."
        )
    if body.shown_to_before_krw is not None and body.shown_to_before_krw != to_before:
        raise HTTPException(
            409, f"고효율 캠페인 예산이 {to_before:,}원으로 바뀌었어요. 제안을 다시 확인해 주세요."
        )
    if (
        from_before - body.from_after_krw != body.move_krw
        or body.to_after_krw - to_before != body.move_krw
    ):
        raise HTTPException(409, "이동 금액이 현재 예산과 맞지 않아요. 제안을 다시 확인해 주세요.")
    if body.from_after_krw < _MIN_DAILY_BUDGET_KRW or body.to_after_krw > _MAX_DAILY_BUDGET_KRW:
        raise HTTPException(
            422,
            f"일예산은 {_MIN_DAILY_BUDGET_KRW:,}~{_MAX_DAILY_BUDGET_KRW:,}원 사이여야 해요.",
        )
    return from_before, to_before


def _build_rebalance_proposal(
    *,
    tenant_id: str,
    ad_account_id: str,
    body: RebalanceCommitRequest,
    from_before: int,
    to_before: int,
) -> ActionProposal:
    """검증 통과한 transfer를 원자 REBALANCE_BUDGET 제안 1건으로 빌드."""
    now = datetime.now(UTC)
    return finalize_proposal(
        ActionProposal(
            proposal_id=f"prop_{uuid4().hex[:8]}",
            tenant_id=tenant_id,
            ad_account_id=ad_account_id,
            target_object_ids=(body.from_campaign_id, body.to_campaign_id),
            action_type="REBALANCE_BUDGET",
            action_tier=judge_tier("REBALANCE_BUDGET"),
            evidence_metrics={
                "source": "rebalance",
                "from_before_krw": from_before,
                "from_after_krw": body.from_after_krw,
                "to_before_krw": to_before,
                "to_after_krw": body.to_after_krw,
                "move_krw": body.move_krw,
            },
            metrics_as_of=now,
            hypothesis="예산 리밸런싱(저효율→고효율) 사용자 승인 집행",
            confidence=1.0,
            expected_state_version="state_v1",
            budget_before_krw=from_before + to_before,
            budget_after_krw=body.from_after_krw + body.to_after_krw,
            max_total_spend_krw=0,  # 총액 불변 — Tier 2 정의와 정합
            expires_at=now + timedelta(minutes=PROPOSAL_TTL_MINUTES),
            approval_policy_version=APPROVAL_POLICY_VERSION,
        )
    )


@router.post("/budget/rebalance-commit")
async def budget_rebalance_commit(
    body: RebalanceCommitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """리밸런싱(transfer) 적용 — 승인 1건·원자 액션 1건으로 감액+증액 집행(보상은 executor)."""
    org_id = await _require_org_id_write(user, db, action="rebalance_commit")
    await _require_owned_campaign(db, org_id, body.from_campaign_id)
    await _require_owned_campaign(db, org_id, body.to_campaign_id)
    reader = await _require_reader(db, org_id)
    from_before, to_before = await _validate_rebalance_change(reader, body)
    ad_account = await _require_ad_account(db, org_id)
    proposal = _build_rebalance_proposal(
        tenant_id=str(org_id),
        ad_account_id=ad_account,
        body=body,
        from_before=from_before,
        to_before=to_before,
    )
    action = await issue_approval(
        proposal, str(user.id), execution_mode=_resolved_execution_mode(), store=_APPROVAL_STORE
    )
    is_demo = proposal.tenant_id == TENANT_ID
    executor = (
        _get_executor()
        if is_demo or getattr(settings, "use_mock", True)
        else _get_executor(await _require_writer(db, org_id))
    )
    result = await executor.execute(action, proposal)
    response: dict[str, object] = {"result": result.model_dump(mode="json")}
    status = result.status.value if hasattr(result.status, "value") else str(result.status)
    if status == "success":
        await _resolve_campaign_notifications(org_id, body.from_campaign_id)
        await _resolve_campaign_notifications(org_id, body.to_campaign_id)
        return response
    comp = _find_in_snapshot(result.platform_response_snapshot, "compensation")
    if comp == "failed":
        # 부분 변경 방치 — 수동 복구 안내가 Meta 원문 에러보다 우선한다.
        response["compensation"] = "failed"
        response["error_message"] = (
            f"예산이 부분 변경됐어요 — 저효율 캠페인 일예산을 {from_before:,}원으로 "
            "수동 복구가 필요해요. 같은 승인으로는 재집행되지 않아요."
        )
        return response
    if comp == "succeeded":
        response["compensation"] = "succeeded"
    msg = _find_in_snapshot(result.platform_response_snapshot, "user_msg")
    if msg:
        response["error_message"] = str(msg)
    elif comp == "succeeded":
        response["error_message"] = (
            "증액에 실패해 감액을 원복했어요. 예산은 원래대로예요 — 잠시 후 다시 시도해 주세요."
        )
    return response
```

주의 — `datetime`·`timedelta`·`uuid4`·`finalize_proposal`·`judge_tier`·`PROPOSAL_TTL_MINUTES`·`APPROVAL_POLICY_VERSION`·`Field`는 이미 파일 상단에 import돼 있다(1-142줄). 신규 import 불필요.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_commit_router.py -v`
Expected: 4개 PASS.

- [ ] **Step 5: 문서 인덱스 갱신** — 라우터 추가 시 자동 생성 스크립트 실행.

Run: `cd backend && uv run python scripts/gen_docs.py`
Expected: `docs/api-endpoints.md`에 `/api/management/budget/rebalance-commit` 추가됨.

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/routers/management.py test/backend/management/test_rebalance_commit_router.py docs/api-endpoints.md
git commit -m "add: /budget/rebalance-commit 엔드포인트 — 양쪽 drift 검증 + 원자 제안 집행"
```

---

### Task 4: 스케줄러 — transfer 알림에 suggested_action 연결

**Files:**
- Modify: `backend/domain/management/scheduler.py:388-429` (`run_rebalance_report`)

- [ ] **Step 1: 구현** — transfer 분기에 `suggested`를 세팅하고 `record_automation_run`에 전달. `record_automation_run`은 `suggested_action: str | None` 파라미터를 이미 받는다(core/automation.py:34).

```python
    move = prop.get("move_krw", 0)
    suggested: str | None = None
    if prop.get("kind") == "adjust":  # 캠페인 1개 — 단일 증액/감액
        camp = prop.get("campaign") or {}
        verb = "증액" if prop.get("direction") == "increase" else "감액"
        body = f"{camp.get('name', '?')} 일예산 {move:,}원 {verb} 제안 (실행은 승인 필요)"
        dedup_key = f"rebalance:{camp.get('campaign_id', '')}:{prop.get('direction', '')}"
    else:  # 캠페인 2개+ — 저효율→고효율 이전(kind 미지정 하위호환 포함)
        frm = prop.get("from") or {}
        to = prop.get("to") or {}
        body = (
            f"{frm.get('name', '?')} → {to.get('name', '?')} 일예산 "
            f"{move:,}원 이동 제안 (실행은 승인 필요)"
        )
        dedup_key = f"rebalance:{frm.get('campaign_id', '')}:{to.get('campaign_id', '')}"
        suggested = "apply_rebalance"  # 챗/알림 카드의 적용 진입 힌트(집행은 HITL 그대로)
    await record_automation_run(
        domain="management",
        job_name="rebalance_proposal",
        title="예산 리밸런싱 제안",
        body=body,
        status="proposal",
        suggested_action=suggested,
        payload={"actor": "auto", "proposal": prop},
        dedup_key=dedup_key,
    )
```

- [ ] **Step 2: 스케줄러 관련 기존 테스트 확인**

Run: `cd backend && uv run pytest ../test/backend/management -k scheduler -v`
Expected: PASS (테스트가 없으면 "no tests ran" — 그대로 진행).

- [ ] **Step 3: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/management/scheduler.py
git commit -m "edit: 리밸런스 transfer 알림에 suggested_action=apply_rebalance 힌트 추가"
```

---

### Task 5: 챗 — `rebalance_action` 위젯 + `apply_rebalance` 툴 + 등록 3곳

**Files:**
- Modify: `backend/domain/chat/widgets.py` (파일 끝에 함수 추가)
- Modify: `backend/api/assistant/subagent_tools.py` (`manage_campaign` 아래 툴 추가 + 1332줄 등록 목록)
- Modify: `backend/api/assistant/prompts.py` (70줄 근처 안내 + 104줄 카드 도구 목록)
- Modify: `backend/domain/management/remediation/contracts.py:13` (ALLOWED_TOOL_HINTS)
- Test: `test/backend/management/test_rebalance_chat.py` (신규)

- [ ] **Step 1: 실패하는 테스트 작성**

```python
# 리밸런스 챗 연결 — rebalance_action 위젯 형태와 tool_hint 허용을 검증
"""위젯 계약(형태 고정)과 remediation tool_hint 등록을 잠근다."""

import pytest
from pydantic import ValidationError

from domain.chat import widgets
from domain.management.remediation.contracts import (
    ALLOWED_TOOL_HINTS,
    OptionKind,
    RemediationAction,
    RemediationOption,
)

_TRANSFER = {
    "kind": "transfer",
    "from": {"campaign_id": "camp_low", "name": "저효율", "cpc_krw": 1200,
             "daily_budget_krw": 50_000, "after_krw": 40_000},
    "to": {"campaign_id": "camp_high", "name": "고효율", "cpc_krw": 800,
           "daily_budget_krw": 30_000, "after_krw": 40_000},
    "move_krw": 10_000,
    "basis": "last_7d",
    "reason": "테스트",
}


def test_rebalance_action_widget_shape():
    out = widgets.rebalance_action(_TRANSFER)
    assert out["source"] == widgets.DEEP_AGENT
    assert out["widget"]["type"] == "rebalance_action"
    assert out["widget"]["data"]["proposal"]["from"]["campaign_id"] == "camp_low"


def test_apply_rebalance_tool_hint_allowed():
    assert "apply_rebalance" in ALLOWED_TOOL_HINTS
    opt = RemediationOption(
        index=1,
        kind=OptionKind.SPEND,
        action=RemediationAction.DECREASE_BUDGET,
        label="리밸런스 적용",
        tool_hint="apply_rebalance",
    )
    assert opt.tool_hint == "apply_rebalance"


def test_unknown_tool_hint_still_rejected():
    with pytest.raises(ValidationError):
        RemediationOption(
            index=1,
            kind=OptionKind.SPEND,
            action=RemediationAction.DECREASE_BUDGET,
            label="오타",
            tool_hint="apply_rebalans",
        )
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_chat.py -v`
Expected: `widgets.rebalance_action` AttributeError, `apply_rebalance not in ALLOWED_TOOL_HINTS`로 FAIL.

- [ ] **Step 3: 구현**

3-a. `backend/domain/chat/widgets.py` 끝에 추가.

```python
def rebalance_action(proposal: dict) -> dict:
    """리밸런싱(transfer) 적용 확인 카드 — proposal=insights kind=transfer 제안 그대로.

    from/to 2개 payload라 campaign_action(단일 캠페인)과 분리한다. source 고정.
    """
    return {
        "widget": {"type": "rebalance_action", "data": {"proposal": proposal}},
        "source": DEEP_AGENT,
    }
```

3-b. `backend/domain/management/remediation/contracts.py:13` 교체.

```python
ALLOWED_TOOL_HINTS = frozenset(
    {"run_generation", "run_simulation", "manage_campaign", "apply_rebalance"}
)
```

3-c. `backend/api/assistant/subagent_tools.py` — `manage_campaign` 툴 정의(1115줄) 바로 아래에 추가. `settings`는 `build_chat_tools(settings, ...)` 클로저로 이미 스코프에 있다.

```python
    @tool
    async def apply_rebalance(
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """'리밸런스/예산 재배분 적용해줘' 요청에 호출. 현재 리밸런싱 제안을 조회해
        적용 확인 카드를 띄운다(집행은 카드에서 사용자 확인 = 승인, 직접 실행 금지)."""
        from domain.management.assistant.tools import live_rebalance_proposal  # noqa: PLC0415

        try:
            data = await live_rebalance_proposal(settings)
        except Exception:  # noqa: BLE001 — 조회 실패는 안내로(카드 없이)
            data = {"proposal": None, "note": "리밸런싱 제안을 불러오지 못했어요."}
        prop = data.get("proposal")
        if not prop:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            data.get("note") or "지금은 리밸런싱 제안이 없어요.",
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
        if prop.get("kind") == "adjust":
            # 단일 증액/감액 — 기존 캠페인 조치 카드(budget-commit 경로) 재사용.
            camp = prop.get("campaign") or {}
            payload = {
                "action": "increase_budget"
                if prop.get("direction") == "increase"
                else "decrease_budget",
                "campaign_id": camp.get("campaign_id", ""),
                "campaign_name": camp.get("name", ""),
                "new_daily_budget_krw": camp.get("after_krw", 0),
            }
            helpers.spawn_record_execution(
                state.get("project_id"),
                "management",
                "rebalance_adjust_request",
                f"리밸런스 단일 조정 요청(카드) {camp.get('name', '')} "
                f"일예산 {camp.get('after_krw', 0)}원",
                {**payload, "stage": "request"},
            )
            return Command(
                update={
                    **widgets.campaign_action(payload),
                    "messages": [
                        ToolMessage(
                            "단일 캠페인 예산 조정 제안이에요. 확인 카드에서 적용해 주세요.",
                            tool_call_id=tool_call_id,
                        )
                    ],
                }
            )
        helpers.spawn_record_execution(
            state.get("project_id"),
            "management",
            "rebalance_request",
            f"리밸런스 적용 요청(카드) {(prop.get('from') or {}).get('name', '')} → "
            f"{(prop.get('to') or {}).get('name', '')} {prop.get('move_krw', 0)}원",
            {"proposal": prop, "stage": "request"},
        )
        return Command(
            update={
                **widgets.rebalance_action(prop),
                "messages": [
                    ToolMessage(
                        "리밸런싱 적용 확인 카드를 준비했어요. 확인해 주세요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
```

등록 목록(1332줄 `return [`)의 `manage_campaign,` 다음 줄에 `apply_rebalance,` 추가.

3-d. `backend/api/assistant/prompts.py` — 70줄 `'새 캠페인 만들기' → create_campaign...` 줄 아래에 추가.

```text
- 예산 '리밸런스/재배분 적용해줘' → apply_rebalance (제안 내용 질문이면 ask_management).
```

104줄 카드 도구 목록의 `create_campaign·manage_campaign·load_template`를 `create_campaign·manage_campaign·apply_rebalance·load_template`로 교체.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest ../test/backend/management/test_rebalance_chat.py -v`
Expected: 3개 PASS.

- [ ] **Step 5: 챗 관련 기존 테스트 회귀 확인**

Run: `cd backend && uv run pytest ../test/backend -k "chat or assistant or remediation" -v`
Expected: 전부 PASS.

- [ ] **Step 6: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/widgets.py backend/api/assistant/subagent_tools.py backend/api/assistant/prompts.py backend/domain/management/remediation/contracts.py test/backend/management/test_rebalance_chat.py
git commit -m "add: 챗 apply_rebalance 툴 + rebalance_action 위젯 (카드 클릭=승인)"
```

---

### Task 6: 프론트 — api.ts + budget 페이지 1-call + 챗 카드

**Files:**
- Modify: `frontend/src/lib/api.ts` — `budgetCommit`(874줄) 아래 `rebalanceCommit` 추가, `RebalanceTransfer` 주석(83줄) 갱신
- Modify: `frontend/src/app/(app)/manage/budget/page.tsx:92-133` — transfer 브랜치 교체
- Create: `frontend/src/components/chat/ChatRebalanceActionCard.tsx`
- Modify: `frontend/src/components/chat/ChatConversation.tsx` — import(38줄 근처) + `campaign_action` 분기(1969줄) 아래 렌더 추가

- [ ] **Step 1: api.ts** — `budgetCommit` 바로 아래에 추가.

```typescript
    // 리밸런싱(transfer) 원자 적용 — 감액+증액+실패 시 보상을 백엔드 1건으로 처리(HITL 승인=이 호출).
    rebalanceCommit: (body: {
      from_campaign_id: string;
      to_campaign_id: string;
      from_after_krw: number;
      to_after_krw: number;
      move_krw: number;
      shown_from_before_krw?: number;
      shown_to_before_krw?: number;
    }) =>
      request<{
        result: ActionResult;
        error_message?: string;
        compensation?: 'succeeded' | 'failed';
      }>(`/management/budget/rebalance-commit`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
```

83줄 `RebalanceTransfer` 주석의 `(적용은 budget-commit 2건)`을 `(적용은 rebalance-commit 1건)`으로 교체.

- [ ] **Step 2: budget 페이지 transfer 브랜치 교체** — `page.tsx`의 `applyRebalance` 내 else 블록(114-124줄)을 교체. adjust 브랜치(100-113줄)는 무변경.

```typescript
      } else {
        // 캠페인 2개+ — 원자 리밸런스 1건(감액→증액→실패 시 보상은 백엔드 executor가 처리).
        const r = await api.management.rebalanceCommit({
          from_campaign_id: rebalance.from.campaign_id,
          to_campaign_id: rebalance.to.campaign_id,
          from_after_krw: rebalance.from.after_krw,
          to_after_krw: rebalance.to.after_krw,
          move_krw: rebalance.move_krw,
          shown_from_before_krw: rebalance.from.daily_budget_krw,
          shown_to_before_krw: rebalance.to.daily_budget_krw,
        });
        if (r.result.status !== 'success') {
          throw new Error(r.error_message ?? '리밸런싱을 적용하지 못했어요.');
        }
        setRebalanceMsg('적용 완료 — 두 캠페인의 일예산을 변경했어요.');
      }
```

함수 상단 주석(92-94줄)도 갱신 — "이전(transfer)은 rebalance-commit 1건(원자·보상 포함), 단일 조정(adjust)은 budget-commit 1건."

- [ ] **Step 3: 챗 카드 컴포넌트 생성** — `frontend/src/components/chat/ChatRebalanceActionCard.tsx`. 스타일·페이즈 구조는 `ChatCampaignActionCard.tsx` 관례를 따른다.

```tsx
// 챗 임베드 리밸런싱 적용 카드 — 확인 클릭 = 승인(HITL) → rebalance-commit 원자 1건 집행.
'use client';

import { useState } from 'react';
import Link from 'next/link';
import { api, type RebalanceTransfer } from '@/lib/api';

type Phase = 'confirm' | 'running' | 'done';

export default function ChatRebalanceActionCard({ proposal }: { proposal: RebalanceTransfer }) {
  const [phase, setPhase] = useState<Phase>('confirm');
  const [ok, setOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setPhase('running');
    setError(null);
    try {
      const r = await api.management.rebalanceCommit({
        from_campaign_id: proposal.from.campaign_id,
        to_campaign_id: proposal.to.campaign_id,
        from_after_krw: proposal.from.after_krw,
        to_after_krw: proposal.to.after_krw,
        move_krw: proposal.move_krw,
        shown_from_before_krw: proposal.from.daily_budget_krw,
        shown_to_before_krw: proposal.to.daily_budget_krw,
      });
      const success = r.result.status === 'success';
      setOk(success);
      if (!success) setError(r.error_message ?? '리밸런싱을 적용하지 못했어요.');
    } catch (e) {
      setOk(false);
      setError(e instanceof Error ? e.message : '요청 중 문제가 발생했어요.');
    }
    setPhase('done');
  };

  if (phase === 'done') {
    return (
      <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
        {ok ? (
          <p className="font-bold text-ink">
            ✓ 리밸런싱 적용 완료 — ₩{proposal.move_krw.toLocaleString()} 이동
          </p>
        ) : (
          <>
            <p className="font-bold text-red-500">리밸런싱 적용 실패</p>
            <p className="mt-1 text-sm text-ink-tertiary">{error ?? '처리되지 않았어요.'}</p>
          </>
        )}
        <Link
          href="/manage/budget"
          className="mt-3 inline-block px-3 py-1.5 bg-primary text-primary-foreground text-xs font-medium rounded-lg hover:bg-primary-hover"
        >
          예산 관리로
        </Link>
      </div>
    );
  }

  return (
    <div className="mt-1 rounded-2xl border border-line p-4 max-w-md">
      <p className="font-bold text-ink mb-2">예산 리밸런싱 적용</p>
      <div className="rounded-xl bg-surface-1 px-4 py-3 text-sm text-ink">
        <p>
          <b>{proposal.from.name}</b>{' '}
          <span className="tabular-nums text-ink-tertiary">
            (₩{proposal.from.daily_budget_krw.toLocaleString()}→₩
            {proposal.from.after_krw.toLocaleString()})
          </span>{' '}
          → <b>{proposal.to.name}</b>{' '}
          <span className="tabular-nums text-ink-tertiary">
            (₩{proposal.to.daily_budget_krw.toLocaleString()}→₩
            {proposal.to.after_krw.toLocaleString()})
          </span>
        </p>
        <p className="mt-1 text-xs text-ink-tertiary">{proposal.reason}</p>
      </div>
      <p className="mt-2 text-xs text-ink-tertiary">
        총 일예산은 그대로예요 — 승인 1건으로 감액과 증액이 함께 집행되고, 증액 실패 시
        자동으로 원복을 시도해요.
      </p>
      <button
        onClick={run}
        disabled={phase !== 'confirm'}
        className="mt-3 px-4 py-2 bg-primary text-primary-foreground text-sm font-medium rounded-lg hover:bg-primary-hover disabled:opacity-40"
      >
        {phase === 'running'
          ? '적용 중…'
          : `₩${proposal.move_krw.toLocaleString()} 이동 적용`}
      </button>
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: ChatConversation 매핑 추가** — `frontend/src/components/chat/ChatConversation.tsx`.

38줄(`import ChatCampaignActionCard ...`) 아래에 import 추가.

```typescript
import ChatRebalanceActionCard from './ChatRebalanceActionCard';
```

`campaign_action` 분기 블록(1969-1984줄) 바로 아래에 추가. `RebalanceTransfer` 타입은 `@/lib/api`에서 import(기존 import 문에 추가).

```tsx
                    {msg.meta?.widget?.type === 'rebalance_action' &&
                      msg.meta.widget.data?.proposal && (
                        <ChatRebalanceActionCard
                          proposal={msg.meta.widget.data.proposal as RebalanceTransfer}
                        />
                      )}
```

- [ ] **Step 5: 빌드 확인**

Run: `cd frontend && pnpm build`
Expected: 빌드 성공(타입 에러 0). `msg.meta.widget.data`의 타입이 좁혀져 있으면 `as` 캐스트 또는 위젯 데이터 타입 정의에 `proposal?: RebalanceTransfer` 추가로 해결.

- [ ] **Step 6: 커밋**

```bash
git add frontend/src/lib/api.ts "frontend/src/app/(app)/manage/budget/page.tsx" frontend/src/components/chat/ChatRebalanceActionCard.tsx frontend/src/components/chat/ChatConversation.tsx
git commit -m "edit: 리밸런스 transfer 적용을 rebalance-commit 1-call로 교체 + 챗 적용 카드 추가"
```

---

### Task 7: 통합 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && uv run pytest ../test/backend -v`
Expected: 전부 PASS.

- [ ] **Step 2: 프론트 린트+빌드**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: 통과.

- [ ] **Step 3: 실계정 선검증 안내 출력(집행은 사람이)** — 코드 작업 아님. 사용자에게 다음을 안내한다.

1. `backend/.env`의 `MANAGEMENT_EXECUTION_MODE=validate_only`로 변경 후 서버 기동.
2. 활성 일예산 캠페인이 2개 이상인지 확인(transfer 제안 발동 조건 — 1개면 테스트 캠페인 추가).
3. `/manage/budget`에서 리밸런싱 제안 적용 → VALIDATE_ONLY라 Meta 검증만 통과하고 실변경 없음 확인.
4. 통과 확인 후 `live` 전환 → 실적용 1회 → 챗에서 "리밸런스 적용해줘"로 카드 흐름 확인.
5. 데모/발표 후 `dry_run` 복귀(CLAUDE.md Open Issue).

- [ ] **Step 4: 스펙 문서 현행화 커밋** — 스펙 §7의 `suggested_action={"type": "rebalance", ...}` 표기를 실제 구현(`suggested_action="apply_rebalance"` 문자열, 제안은 payload)에 맞게 수정.

```bash
git add docs/superpowers/specs/2026-07-11-rebalance-transfer-execution-design.md
git commit -m "edit: 리밸런스 스펙 — suggested_action 문자열 시그니처로 현행화"
```
