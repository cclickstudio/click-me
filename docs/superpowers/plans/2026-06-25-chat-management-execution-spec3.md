# 매니지먼트 챗 제안 집행 브릿지 (스펙3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매니지먼트 챗 카드의 `proposal_preview`(비실행)를 명시적 버튼 → finalize(정본 승격) → 서버 orchestration(approve/execute) → `execution_result` 카드로 한 흐름에 닫는다.

**Architecture:** 클라는 `proposal_id`만 들고, 서버 라우터가 기존 `approve()`·`executor.execute()`를 호출한다. finalize는 최신 진단(`live_diagnosis`)으로 정본 `ActionProposal`을 만들어 `action_proposals`에 영속하고, decision은 그 정본을 로드해 집행한 뒤 `ActionResult`로 결과 카드를 결정적으로 만든다. `approval.py`·`executor.py`·`detection/`·`ActionProposal`(18필드)은 미수정.

**Tech Stack:** FastAPI · SQLAlchemy async · Pydantic v2 · pytest(백엔드) · Next.js/TS(프론트). 설계 정본: `docs/superpowers/specs/2026-06-25-chat-management-execution-spec3-design.md`.

---

## 참조 — 기존 시그니처 (구현 중 의존)

- `domain/management/contracts/schemas.py`: `ActionProposal`(18필드), `finalize_proposal(p)->p`, `verify_proposal_hash`, `ActionResult{result_id,approval_id,status,failure_reason,platform_response_snapshot,executed_at,idempotency_key}`, `ApprovedAction`, `AUTO_APPROVER`.
- `domain/management/contracts/enums.py`: `ActionTier`(IntEnum TIER_0..TIER_3), `ResultStatus`(SUCCESS/FAILED/REJECTED/SUBMITTED_PENDING_REVIEW), `FailureReason`(PROPOSAL_EXPIRED/APPROVAL_EXPIRED/STALE_PROPOSAL/…), `ProposalStatus`(DRAFT/PENDING/APPROVED/REJECTED/EXPIRED/EXECUTED/STALE), `ExecutionMode`.
- `domain/management/assistant/contracts.py`: `DiagnosticResult{diagnostic_status,anomaly,diagnosis:DiagnosisView,proposal_preview:ProposalPreview,reason}`, `DiagnosisView{anomaly_type,status,confidence,hypothesis}`, `ProposalPreview{preview_id,action_type,tier,budget_before_krw,budget_after_krw,hypothesis}`.
- `domain/management/assistant/tools.py`: `async live_diagnosis(settings, campaign_id, tenant_id=None) -> DiagnosticResult`.
- `domain/management/approval.py`: `approve(proposal, approver_id, execution_mode) -> ApprovedAction`, `validate_proposal(proposal) -> list[issue]`.
- `api/routers/management.py`: `_require_org_id(user, db)->org_id`, `_require_ad_account(db, org_id)->str`, `_get_executor(writer=None)->Executor`, `_resolved_execution_mode()->ExecutionMode`, `_require_writer(db, org_id)`. (one-way import from chat_management 허용 — management는 chat_management를 import하지 않음.)
- `domain/management/contracts/policy.py`: `APPROVAL_POLICY_VERSION`, `DAILY_BUDGET_KRW`.
- `domain/management/demo.py`: `TENANT_ID`, `CAMPAIGN_ID`.
- `core/models.py`: `ActionProposalRow`(action_proposals), `AuditEventRow`(audit_events), `ManagementChatMessage`(management_chat_messages).
- 프론트: `frontend/src/lib/chatCard.ts`(타입), `frontend/src/components/chat/sections.tsx`(SECTION_RENDERERS), `frontend/src/components/chat/ChatCardView.tsx`.

---

## File Structure

| 파일 | 신규/수정 | 책임 |
|---|---|---|
| `backend/domain/management/assistant/chat_cards/models.py` | 수정 | `ExecutionResultSection` 추가 → `CardSection` union |
| `backend/domain/management/assistant/contracts.py` | 수정 | `FinalizeResult` 추가 |
| `backend/domain/management/execution/proposal_builder.py` | 신규 | `build_action_proposal_from_diagnosis(...)` + `requires_external_approval(tier)` |
| `backend/domain/management/execution/service/proposal_store.py` | 신규 | async `ProposalStore`(ActionProposalRow CRUD) |
| `backend/domain/management/assistant/result_card.py` | 신규 | `build_execution_result_card(...)` + 상태 매핑(ActionResult→result_status) |
| `backend/api/routers/chat_management.py` | 신규 | `/proposals/finalize`, `/proposals/{id}/decision` |
| `backend/api/main.py` | 수정 | include_router 1줄(append-only) |
| `backend/api/routers/chat.py` | 수정 | `/sessions/{id}/messages` 스텁 → 저장 카드 역직렬화 |
| `backend/tests/management/test_chat_execution_bridge.py` | 신규 | 백엔드 게이트 테스트 |
| `frontend/src/lib/chatCard.ts` | 수정 | `execution_result` 섹션 타입 + finalize/decision API 타입 |
| `frontend/src/lib/managementActions.ts` | 신규 | finalize/decision fetch 클라이언트 |
| `frontend/src/components/chat/sections.tsx` | 수정 | `execution_result` 렌더러 |
| `frontend/src/components/chat/ProposalActions.tsx` | 신규 | 버튼·상태(로딩·TTL·drift·거절·실패) |
| `frontend/src/components/chat/ChatCardView.tsx` | 수정 | proposal 섹션에 ProposalActions 연결 |

---

## Phase A — 백엔드 계약·빌더 (TDD)

### Task 1: `ExecutionResultSection` 카드 계약

**Files:**
- Modify: `backend/domain/management/assistant/chat_cards/models.py`
- Test: `backend/tests/management/test_chat_cards.py` (없으면 생성)

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/management/test_chat_cards.py
from domain.management.assistant.chat_cards.models import ChatCard, ExecutionResultSection


def test_execution_result_section_in_card():
    sec = ExecutionResultSection(
        title="집행 결과",
        action_type="INCREASE_BUDGET",
        result_status="success",
        proposal_id="prop_1",
        budget_before_krw=10000,
        budget_after_krw=15000,
        run_id=None,
        summary="일예산을 10,000원에서 15,000원으로 올렸어요.",
    )
    card = ChatCard(type="management", status="ok", sections=[sec])
    dumped = card.model_dump()
    assert dumped["sections"][0]["kind"] == "execution_result"
    assert dumped["sections"][0]["proposal_id"] == "prop_1"
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_cards.py -v`
Expected: FAIL (`ImportError: cannot import name 'ExecutionResultSection'`)

- [ ] **Step 3: 구현**

`models.py`의 `DiagnosisSection` 정의 다음에 추가:

```python
class ExecutionResultSection(BaseModel):
    kind: Literal["execution_result"] = "execution_result"
    title: str | None = None
    action_type: str
    result_status: Literal[
        "success", "submitted_pending_review", "failed", "rejected", "expired", "already_executed"
    ]
    proposal_id: str
    preview_id: str | None = None
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    run_id: str | None = None
    summary: str
    failure_reason: str | None = None
```

그리고 `CardSection` union에 `| ExecutionResultSection` 추가:

```python
CardSection = Annotated[
    SummarySection
    | MetricsSection
    | EntitySection
    | ProposalSection
    | ReviewSection
    | EvidenceSection
    | EmptyStateSection
    | DiagnosisSection
    | ExecutionResultSection,
    Field(discriminator="kind"),
]
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_cards.py -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/assistant/chat_cards/models.py backend/tests/management/test_chat_cards.py
git commit -m "add: execution_result 카드 섹션 계약 (스펙3)"
```

---

### Task 2: `FinalizeResult` 로컬 계약

**Files:**
- Modify: `backend/domain/management/assistant/contracts.py`
- Test: `backend/tests/management/test_chat_execution_bridge.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/management/test_chat_execution_bridge.py
from domain.management.assistant.contracts import FinalizeResult


def test_finalize_result_finalized_carries_proposal_id():
    r = FinalizeResult(
        status="finalized", proposal_id="prop_1", action_type="INCREASE_BUDGET",
        tier="TIER_2", requires_external_approval=False,
        budget_before_krw=10000, budget_after_krw=15000,
        summary="제안 준비됨", expires_at="2026-06-25T12:00:00Z", drift=False,
    )
    assert r.status == "finalized" and r.proposal_id == "prop_1"


def test_finalize_result_unavailable_needs_no_proposal():
    r = FinalizeResult(status="unavailable", reason="데이터 부족")
    assert r.proposal_id is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_chat_execution_bridge.py -v`
Expected: FAIL (`ImportError`)

- [ ] **Step 3: 구현** — `contracts.py` 끝에 추가:

```python
class FinalizeResult(BaseModel):
    """finalize 응답 — 정본 본문(ActionProposal) 미포함(서버 DB에만)."""

    status: Literal["finalized", "unavailable", "no_anomaly"]
    proposal_id: str | None = None
    action_type: str | None = None
    tier: str | None = None
    requires_external_approval: bool = False
    budget_before_krw: int | None = None
    budget_after_krw: int | None = None
    summary: str | None = None
    expires_at: str | None = None  # ISO8601
    drift: bool = False
    reason: str = ""  # unavailable/no_anomaly 안전 문구
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/assistant/contracts.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: FinalizeResult 로컬 계약 (스펙3)"
```

---

### Task 3: 정본 proposal 빌더

**Files:**
- Create: `backend/domain/management/execution/proposal_builder.py`
- Test: `backend/tests/management/test_chat_execution_bridge.py` (추가)

- [ ] **Step 1: 실패 테스트 작성** (파일에 추가)

```python
from datetime import UTC, datetime, timedelta

from domain.management.assistant.contracts import DiagnosisView, DiagnosticResult, ProposalPreview
from domain.management.contracts.enums import ActionTier, ProposalStatus
from domain.management.contracts.schemas import verify_proposal_hash
from domain.management.execution.proposal_builder import (
    build_action_proposal_from_diagnosis,
    requires_external_approval,
)


def _ok_anomaly_dx(action="INCREASE_BUDGET", tier="TIER_2"):
    return DiagnosticResult(
        diagnostic_status="ok", anomaly=True,
        diagnosis=DiagnosisView(anomaly_type="budget_exhausted", status="confirmed",
                                confidence=0.9, hypothesis="예산 소진"),
        proposal_preview=ProposalPreview(preview_id="preview_x", action_type=action, tier=tier,
                                         budget_before_krw=10000, budget_after_krw=15000,
                                         hypothesis="예산 소진"),
    )


def test_builder_promotes_preview_to_finalized_proposal():
    now = datetime(2026, 6, 25, tzinfo=UTC)
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(), tenant_id="org_1", ad_account_id="act_1", campaign_id="camp_1",
        expected_state_version="state_v1", approval_policy_version="v1",
        run_days=7, ttl=timedelta(minutes=10), now=now,
    )
    assert p.proposal_id != "preview_x"          # 정본 ID는 preview_id 재사용 안 함(테스트7)
    assert p.action_type == "INCREASE_BUDGET"
    assert p.action_tier == ActionTier.TIER_2
    assert p.budget_before_krw == 10000 and p.budget_after_krw == 15000
    assert p.max_total_spend_krw == 15000 * 7
    assert p.status == ProposalStatus.PENDING
    assert verify_proposal_hash(p)               # finalize_proposal 해시 채워짐


def test_requires_external_approval_for_tier3():
    assert requires_external_approval(ActionTier.TIER_3) is True
    assert requires_external_approval(ActionTier.TIER_2) is False
```

- [ ] **Step 2: 실패 확인** → FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: 구현**

```python
# backend/domain/management/execution/proposal_builder.py
# DiagnosticResult(최신 진단)의 proposal_preview를 정본 ActionProposal로 승격한다.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from domain.management.assistant.contracts import DiagnosticResult
from domain.management.contracts.enums import ActionTier, ProposalStatus
from domain.management.contracts.schemas import ActionProposal, finalize_proposal

#: 챗 버튼(단일 승인)으로 집행 가능한 최대 Tier. 초과(예: TIER_3)는 정식 승인 필요(§5.4).
#: 정책 권위는 approval.py — 이 컷오프는 FE 노출용 신호이며 approve()가 최종 강제한다.
CHAT_EXECUTABLE_MAX_TIER = ActionTier.TIER_2


def requires_external_approval(tier: ActionTier) -> bool:
    return tier > CHAT_EXECUTABLE_MAX_TIER


def build_action_proposal_from_diagnosis(
    dx: DiagnosticResult,
    *,
    tenant_id: str,
    ad_account_id: str,
    campaign_id: str,
    expected_state_version: str,
    approval_policy_version: str,
    preview_id: str | None = None,
    run_days: int = 7,
    ttl: timedelta = timedelta(minutes=10),
    now: datetime | None = None,
) -> ActionProposal:
    """ok+anomaly DiagnosticResult → finalize된 정본 ActionProposal. 호출 전 ok+anomaly 보장."""
    if dx.diagnostic_status != "ok" or not dx.anomaly or dx.proposal_preview is None:
        raise ValueError("build_action_proposal_from_diagnosis는 ok+anomaly에서만 호출")
    now = now or datetime.now(UTC)
    pv = dx.proposal_preview
    tier = ActionTier[pv.tier] if pv.tier else ActionTier.TIER_2
    budget_after = pv.budget_after_krw or 0
    return finalize_proposal(
        ActionProposal(
            proposal_id=str(uuid4()),
            tenant_id=tenant_id,
            ad_account_id=ad_account_id,
            target_object_ids=(campaign_id,),
            action_type=pv.action_type,
            action_tier=tier,
            # preview_id는 trace용(ActionProposal 18필드 잠금 → evidence_metrics에 보관, §4)
            evidence_metrics={"source": "chat_finalize",
                              "confidence": dx.diagnosis.confidence if dx.diagnosis else 0.0,
                              "preview_id": preview_id},
            metrics_as_of=now,
            hypothesis=dx.diagnosis.hypothesis if dx.diagnosis else "",
            confidence=dx.diagnosis.confidence if dx.diagnosis else 0.0,
            expected_state_version=expected_state_version,
            budget_before_krw=pv.budget_before_krw or 0,
            budget_after_krw=budget_after,
            max_total_spend_krw=budget_after * run_days,
            expires_at=now + ttl,
            approval_policy_version=approval_policy_version,
            status=ProposalStatus.PENDING,
        )
    )
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/execution/proposal_builder.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: 진단→정본 ActionProposal 빌더 (스펙3)"
```

---

### Task 4: async `ProposalStore` (action_proposals 영속)

**Files:**
- Create: `backend/domain/management/execution/service/proposal_store.py`
- Test: `backend/tests/management/test_chat_execution_bridge.py` (추가, DB 픽스처 사용)

> 기존 `ExecutionService.ProposalRepository`(sync, in-memory)는 챗 경로에 없다. 챗 라우터는 AsyncSession으로 직접 영속/조회하므로 async store를 별도로 둔다(스펙 §5#3을 async로 실체화).

- [ ] **Step 1: 실패 테스트 작성** (DB 세션 픽스처는 기존 conftest 재사용 — `db_session`)

```python
import pytest

from domain.management.execution.service.proposal_store import ProposalStore


@pytest.mark.asyncio
async def test_proposal_store_roundtrip(db_session):
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(), tenant_id="org_1", ad_account_id="act_1", campaign_id="camp_1",
        expected_state_version="state_v1", approval_policy_version="v1",
    )
    store = ProposalStore(db_session)
    await store.save(p)
    loaded = await store.get(p.proposal_id)
    assert loaded is not None
    assert loaded.proposal_id == p.proposal_id
    assert loaded.proposal_hash == p.proposal_hash   # 라운드트립 변조 없음
    assert verify_proposal_hash(loaded)
```

> conftest에 `db_session` 픽스처가 없으면, 같은 파일에 SQLite/Neon 테스트 세션 픽스처를 추가하거나 기존 management 테스트의 DB 픽스처 패턴을 그대로 가져온다(없으면 이 태스크 1단계에서 픽스처부터 추가).

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현**

```python
# backend/domain/management/execution/service/proposal_store.py
# action_proposals 테이블에 ActionProposal 정본을 영속/조회(async). 판정·조인 신호는 컬럼, 나머지는 payload.
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import ActionProposalRow
from domain.management.contracts.enums import ActionTier, ProposalStatus
from domain.management.contracts.schemas import ActionProposal


class ProposalStore:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def save(self, p: ActionProposal) -> None:
        self._db.add(
            ActionProposalRow(
                proposal_id=p.proposal_id,
                tenant_id=p.tenant_id,
                ad_account_id=p.ad_account_id,
                action_type=p.action_type,
                action_tier=int(p.action_tier),
                status=p.status.value,  # StrEnum .value 명시 — "pending"으로 저장(복원 일치)
                budget_before_krw=p.budget_before_krw,
                budget_after_krw=p.budget_after_krw,
                max_total_spend_krw=p.max_total_spend_krw,
                expected_state_version=p.expected_state_version,
                proposal_hash=p.proposal_hash,
                approval_policy_version=p.approval_policy_version,
                expires_at=p.expires_at,
                payload={
                    "evidence_metrics": p.evidence_metrics,
                    "hypothesis": p.hypothesis,
                    "confidence": p.confidence,
                    "metrics_as_of": p.metrics_as_of.isoformat(),
                    "target_object_ids": list(p.target_object_ids),
                },
            )
        )
        await self._db.commit()

    async def get(self, proposal_id: str) -> ActionProposal | None:
        row = (
            await self._db.execute(
                select(ActionProposalRow).where(ActionProposalRow.proposal_id == proposal_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        pl = row.payload or {}
        return ActionProposal(
            proposal_id=row.proposal_id,
            tenant_id=row.tenant_id,
            ad_account_id=row.ad_account_id,
            target_object_ids=tuple(pl.get("target_object_ids", [])),
            action_type=row.action_type,
            action_tier=ActionTier(row.action_tier),
            evidence_metrics=pl.get("evidence_metrics", {}),
            metrics_as_of=datetime.fromisoformat(pl["metrics_as_of"]),
            hypothesis=pl.get("hypothesis", ""),
            confidence=pl.get("confidence", 0.0),
            expected_state_version=row.expected_state_version,
            budget_before_krw=row.budget_before_krw,
            budget_after_krw=row.budget_after_krw,
            max_total_spend_krw=row.max_total_spend_krw,
            expires_at=row.expires_at,
            proposal_hash=row.proposal_hash,
            approval_policy_version=row.approval_policy_version,
            status=ProposalStatus(row.status),
        )

    async def set_status(self, proposal_id: str, status: ProposalStatus) -> None:
        row = (
            await self._db.execute(
                select(ActionProposalRow).where(ActionProposalRow.proposal_id == proposal_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            row.status = status.value
            await self._db.commit()

    async def try_claim(self, proposal_id: str) -> bool:
        """원자적 PENDING→APPROVED 전이. 정확히 1회만 True(동시 요청·중복 클릭 가드).

        executor 내부 멱등(approval_id 파생)은 approve()마다 키가 바뀌어 요청 간 보장이 약하므로,
        proposal_id 단위 compare-and-set이 cross-request 정확히-1회의 정본 가드다(스펙 §6).
        """
        res = await self._db.execute(
            update(ActionProposalRow)
            .where(
                ActionProposalRow.proposal_id == proposal_id,
                ActionProposalRow.status == ProposalStatus.PENDING.value,
            )
            .values(status=ProposalStatus.APPROVED.value)
        )
        await self._db.commit()
        return res.rowcount == 1
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/execution/service/proposal_store.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: ProposalStore — action_proposals async 영속/조회 (스펙3)"
```

---

### Task 5: 결과 카드 빌더 + 상태 매핑

**Files:**
- Create: `backend/domain/management/assistant/result_card.py`
- Test: `backend/tests/management/test_chat_execution_bridge.py` (추가)

- [ ] **Step 1: 실패 테스트 작성**

```python
from domain.management.contracts.enums import FailureReason, ResultStatus
from domain.management.contracts.schemas import ActionResult
from domain.management.assistant.result_card import (
    map_result_status, build_execution_result_card,
)


def test_map_result_status_covers_failure_reasons():
    assert map_result_status(ResultStatus.SUCCESS, None) == "success"
    assert map_result_status(ResultStatus.SUBMITTED_PENDING_REVIEW, None) == "submitted_pending_review"
    assert map_result_status(ResultStatus.REJECTED, None) == "rejected"
    assert map_result_status(ResultStatus.FAILED, FailureReason.PROPOSAL_EXPIRED) == "expired"
    assert map_result_status(ResultStatus.FAILED, FailureReason.STALE_PROPOSAL) == "already_executed"
    assert map_result_status(ResultStatus.FAILED, FailureReason.PLATFORM_ERROR) == "failed"


def test_build_card_from_action_result_and_proposal():
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(), tenant_id="org_1", ad_account_id="act_1", campaign_id="camp_1",
        expected_state_version="state_v1", approval_policy_version="v1",
    )
    result = ActionResult(result_id="r1", approval_id="ap1", status=ResultStatus.SUCCESS,
                          idempotency_key="idem1")
    card = build_execution_result_card(proposal=p, result=result, run_id=None, turn_id="t1")
    sec = card.model_dump()["sections"][0]
    assert sec["kind"] == "execution_result"
    assert sec["result_status"] == "success"
    assert sec["proposal_id"] == p.proposal_id
    assert sec["budget_before_krw"] == 10000 and sec["budget_after_krw"] == 15000
    assert card.status == "ok"
```

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현**

```python
# backend/domain/management/assistant/result_card.py
# 집행 결과를 ActionResult + 영속 ActionProposal로 결정적 카드화(LLM 미경유, 스펙 §5.5).
from __future__ import annotations

from domain.management.assistant.chat_cards.models import ChatCard, ExecutionResultSection, TraceInfo
from domain.management.contracts.enums import FailureReason, ResultStatus
from domain.management.contracts.schemas import ActionProposal, ActionResult

_EXPIRED = {FailureReason.PROPOSAL_EXPIRED, FailureReason.APPROVAL_EXPIRED}

_CARD_STATUS = {
    "success": "ok",
    "submitted_pending_review": "warning",
    "failed": "critical",
    "rejected": "neutral",
    "expired": "neutral",
    "already_executed": "neutral",
}

_FAILURE_TEXT = {
    "failed": "집행 중 문제가 발생해 적용되지 않았어요.",
    "expired": "제안이 만료돼 집행하지 않았어요. 다시 진단해 주세요.",
    "rejected": "정책상 챗에서 바로 집행할 수 없어요. 정식 승인 화면에서 처리해 주세요.",
    "already_executed": "이미 처리된 제안이에요.",
}


def map_result_status(status: ResultStatus, failure_reason: FailureReason | None) -> str:
    if status == ResultStatus.SUCCESS:
        return "success"
    if status == ResultStatus.SUBMITTED_PENDING_REVIEW:
        return "submitted_pending_review"
    if status == ResultStatus.REJECTED:
        return "rejected"
    if failure_reason in _EXPIRED:
        return "expired"
    if failure_reason == FailureReason.STALE_PROPOSAL:
        return "already_executed"
    return "failed"


def _summary(result_status: str, p: ActionProposal) -> str:
    if result_status == "success":
        return (f"일예산을 {p.budget_before_krw:,}원에서 {p.budget_after_krw:,}원으로 조정했어요."
                if p.action_type in ("INCREASE_BUDGET", "DECREASE_BUDGET")
                else f"{p.action_type} 집행을 완료했어요.")
    if result_status == "submitted_pending_review":
        return "Meta에 제출했고 검토 중이에요."
    return _FAILURE_TEXT.get(result_status, "처리되지 않았어요.")


def build_execution_result_card(
    *, proposal: ActionProposal, result: ActionResult | None,
    run_id: str | None, turn_id: str, result_status: str | None = None,
) -> ChatCard:
    """result가 있으면 그 status로, 없으면(실행 전 terminal) result_status 인자로 카드를 만든다."""
    rs = result_status or map_result_status(result.status, result.failure_reason) if result else result_status
    assert rs is not None, "result 또는 result_status 중 하나는 필요"
    sec = ExecutionResultSection(
        title="집행 결과",
        action_type=proposal.action_type,
        result_status=rs,
        proposal_id=proposal.proposal_id,
        preview_id=proposal.evidence_metrics.get("preview_id"),  # trace(§4): preview_id→proposal_id→run_id
        budget_before_krw=proposal.budget_before_krw,
        budget_after_krw=proposal.budget_after_krw,
        run_id=run_id,
        summary=_summary(rs, proposal),
        failure_reason=(_FAILURE_TEXT.get(rs) if rs not in ("success", "submitted_pending_review") else None),
    )
    return ChatCard(type="management", status=_CARD_STATUS[rs], sections=[sec],
                    trace=TraceInfo(turn_id=turn_id))
```

- [ ] **Step 4: 통과 확인** → PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/domain/management/assistant/result_card.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: 집행 결과 카드 빌더 + 상태 매핑 (스펙3)"
```

---

## Phase B — 라우터·배선

### Task 6: chat_management 라우터 — finalize

**Files:**
- Create: `backend/api/routers/chat_management.py`
- Test: `backend/tests/management/test_chat_execution_bridge.py` (추가, FastAPI TestClient + dependency_overrides)

- [ ] **Step 1: 실패 테스트 작성** — `live_diagnosis`를 monkeypatch해 ok+anomaly를 강제하고, finalize가 PENDING proposal을 저장하고 `proposal_id != preview_id`를 반환하는지.

```python
import pytest
from httpx import ASGITransport, AsyncClient

from api.main import app
from core.auth import get_current_user
from core.db import get_db


@pytest.mark.asyncio
async def test_finalize_persists_pending_and_returns_new_proposal_id(db_session, monkeypatch):
    async def fake_diag(settings, campaign_id, tenant_id=None):
        return _ok_anomaly_dx()
    monkeypatch.setattr("api.routers.chat_management.live_diagnosis", fake_diag)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post("/api/chat/management/proposals/finalize",
                              json={"preview_id": "preview_x", "campaign_id": "camp_1",
                                    "thread_id": "mgmt-s1", "shown_budget_after_krw": 15000})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "finalized"
        assert body["proposal_id"] != "preview_x"
        store = ProposalStore(db_session)
        saved = await store.get(body["proposal_id"])
        assert saved is not None and str(saved.status) == "pending"
    finally:
        app.dependency_overrides.clear()
```

> `_fake_user()`는 use_mock=True 데모 경로를 타도록 구성(테넌트=TENANT_ID). `db_session`/`_fake_user` 헬퍼가 없으면 이 단계에서 conftest에 추가.

- [ ] **Step 2: 실패 확인** → FAIL (404 또는 ImportError)

- [ ] **Step 3: 구현** — finalize 엔드포인트

```python
# backend/api/routers/chat_management.py
# 챗 카드 proposal_preview → 정본 finalize → (decision에서) approve/execute. 정본 본문은 서버에만.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.routers.management import _require_ad_account, _require_org_id
from core.auth import User, get_current_user
from core.config import settings
from core.db import get_db
from domain.management.assistant.contracts import FinalizeResult
from domain.management.assistant.tools import live_diagnosis
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION
from domain.management.demo import TENANT_ID
from domain.management.execution.proposal_builder import (
    build_action_proposal_from_diagnosis,
    requires_external_approval,
)
from domain.management.execution.service.proposal_store import ProposalStore

router = APIRouter()

_TTL = timedelta(minutes=10)


class FinalizeRequest(BaseModel):
    preview_id: str | None = None   # trace/anti-stale (lookup 아님)
    campaign_id: str
    thread_id: str | None = None
    shown_budget_after_krw: int | None = None  # drift 비교용(신뢰 아님)
    shown_at: str | None = None
    preview_fingerprint: str | None = None


async def _resolve_tenant_account(user: User, db: AsyncSession) -> tuple[str, str]:
    """데모(use_mock)는 센티넬 테넌트·데모 계정, 실측은 로그인 org/연결 계정."""
    if getattr(settings, "use_mock", True):
        return TENANT_ID, "act_demo"
    org_id = await _require_org_id(user, db)
    return str(org_id), await _require_ad_account(db, org_id)


@router.post("/proposals/finalize")
async def finalize_proposal_endpoint(
    body: FinalizeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FinalizeResult:
    tenant_id, ad_account_id = await _resolve_tenant_account(user, db)  # finalize 시점 authz
    dx = await live_diagnosis(settings, body.campaign_id, tenant_id)
    if dx.diagnostic_status != "ok":
        return FinalizeResult(status="unavailable", reason=dx.reason or "진단할 수 없어요.")
    if not dx.anomaly or dx.proposal_preview is None:
        return FinalizeResult(status="no_anomaly", reason="더 이상 조치가 필요한 이상이 없어요.")

    now = datetime.now(UTC)
    proposal = build_action_proposal_from_diagnosis(
        dx, tenant_id=tenant_id, ad_account_id=ad_account_id, campaign_id=body.campaign_id,
        expected_state_version="state_v1", approval_policy_version=APPROVAL_POLICY_VERSION,
        preview_id=body.preview_id, ttl=_TTL, now=now,
    )
    await ProposalStore(db).save(proposal)  # requires_external_approval여도 PENDING 영속(§5.4)

    drift = (body.shown_budget_after_krw is not None
             and body.shown_budget_after_krw != proposal.budget_after_krw)
    return FinalizeResult(
        status="finalized", proposal_id=proposal.proposal_id, action_type=proposal.action_type,
        tier=proposal.action_tier.name,
        requires_external_approval=requires_external_approval(proposal.action_tier),
        budget_before_krw=proposal.budget_before_krw, budget_after_krw=proposal.budget_after_krw,
        summary=f"{proposal.action_type} 제안을 준비했어요.",
        expires_at=proposal.expires_at.isoformat(), drift=drift,
    )
```

main.py 등록은 Task 8에서. 테스트가 앱 라우트를 찾으려면 Task 8의 include를 먼저 해도 되고, 이 단계에서 함께 등록해도 된다(아래 Task 8 Step과 동일 1줄).

- [ ] **Step 4: 통과 확인** (Task 8의 include 적용 후) → PASS
- [ ] **Step 5: 커밋**

```bash
git add backend/api/routers/chat_management.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: chat_management finalize 엔드포인트 (스펙3)"
```

---

### Task 7: decision 엔드포인트 (approve/reject + 가드)

**Files:**
- Modify: `backend/api/routers/chat_management.py`
- Test: `backend/tests/management/test_chat_execution_bridge.py` (추가)

- [ ] **Step 1: 실패 테스트 작성** — (1) approve 성공 → success 카드, (2) 만료 proposal → expired 카드(executor 미호출), (3) reject → rejected 카드 + 멱등, (4) 같은 idempotency_key 2회 → executor 1회.

```python
@pytest.mark.asyncio
async def test_decision_approve_returns_success_card(db_session, monkeypatch):
    # finalize로 PENDING 저장
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(), tenant_id=TENANT_ID, ad_account_id="act_demo", campaign_id="camp_1",
        expected_state_version="state_v1", approval_policy_version="v1")
    await ProposalStore(db_session).save(p)

    calls = {"n": 0}
    async def fake_execute(approved, proposal):
        calls["n"] += 1
        from domain.management.contracts.enums import ResultStatus
        from domain.management.contracts.schemas import ActionResult
        return ActionResult(result_id="r1", approval_id="ap1", status=ResultStatus.SUCCESS,
                            idempotency_key="idem1")
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            r = await ac.post(f"/api/chat/management/proposals/{p.proposal_id}/decision",
                              json={"decision": "approve", "idempotency_key": "idem1",
                                    "thread_id": "mgmt-s1"})
        assert r.status_code == 200
        card = r.json()
        assert card["sections"][0]["kind"] == "execution_result"
        assert card["sections"][0]["result_status"] == "success"
        assert calls["n"] == 1
    finally:
        app.dependency_overrides.clear()
```

추가 테스트(같은 패턴):
- **만료**: `expires_at`을 과거로 저장 → approve 호출 시 `expired` 카드, executor 미호출.
- **reject 멱등**: decision="reject" → `rejected`, executor 미호출. 같은 proposal에 reject 2회 → status REJECTED 유지·에러 없음.
- **Tier3 서버 가드**(P1-3): `tier="TIER_3"`인 `_ok_anomaly_dx`로 finalize·저장 후 decision="approve" → `rejected` 카드, **`_execute` 미호출**(`calls["n"]==0`). FE 없이도 차단됨.
- **병렬 중복 정확히-1회**(P1-2): 같은 proposal_id로 `decision="approve"`를 `asyncio.gather`로 10개 동시 호출 → `_execute`는 **정확히 1회**(`calls["n"]==1`), 나머지 9개는 `already_executed` 카드. (각 호출은 새 idempotency_key여도 try_claim이 1회만 통과.)

```python
@pytest.mark.asyncio
async def test_concurrent_decisions_execute_exactly_once(db_session, monkeypatch):
    p = build_action_proposal_from_diagnosis(
        _ok_anomaly_dx(), tenant_id=TENANT_ID, ad_account_id="act_demo", campaign_id="camp_1",
        expected_state_version="state_v1", approval_policy_version="v1")
    await ProposalStore(db_session).save(p)
    calls = {"n": 0}
    async def fake_execute(approved, proposal, idempotency_key):
        calls["n"] += 1
        from domain.management.contracts.enums import ResultStatus
        from domain.management.contracts.schemas import ActionResult
        return ActionResult(result_id="r", approval_id="ap", status=ResultStatus.SUCCESS, idempotency_key=idempotency_key)
    monkeypatch.setattr("api.routers.chat_management._execute", fake_execute)
    app.dependency_overrides[get_current_user] = lambda: _fake_user()
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        import asyncio
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
            from uuid import uuid4
            async def fire():
                return await ac.post(f"/api/chat/management/proposals/{p.proposal_id}/decision",
                                     json={"decision": "approve", "idempotency_key": uuid4().hex, "thread_id": "mgmt-s1"})
            await asyncio.gather(*[fire() for _ in range(10)])
        assert calls["n"] == 1
    finally:
        app.dependency_overrides.clear()
```

> 병렬 테스트는 동일 `db_session`을 공유하면 SQLite 동시성 한계로 흔들릴 수 있다. Neon(Postgres) 테스트 DB거나, 세션당 분리 연결 픽스처에서 `try_claim`의 `UPDATE ... WHERE status='pending'` 원자성이 보장돼야 한다(게이트 정본). conftest 픽스처가 동시성을 못 받치면 Task4에서 Postgres 테스트 세션으로 보강.

- [ ] **Step 2: 실패 확인** → FAIL

- [ ] **Step 3: 구현** — decision 엔드포인트 + 내부 `_execute`(테스트 monkeypatch 지점)

```python
# chat_management.py 에 추가
from uuid import uuid4

from domain.management.approval import approve
from domain.management.assistant.chat_cards.models import (
    ChatCard, ExecutionResultSection, TraceInfo,
)
from domain.management.assistant.result_card import build_execution_result_card, map_result_status
from domain.management.contracts.enums import ProposalStatus
from domain.management.contracts.schemas import ActionResult, AUTO_APPROVER
from domain.management.execution.executor import Executor
from domain.management.execution.proposal_builder import requires_external_approval


class DecisionRequest(BaseModel):
    decision: str            # "approve" | "reject"
    idempotency_key: str     # (proposal_id, idempotency_key) scope — 같은 클릭 재시도는 동일 값
    thread_id: str | None = None


async def _execute(approved, proposal, idempotency_key: str) -> ActionResult:
    """executor 호출 격리 지점(테스트 monkeypatch). 기존 /execute와 동일 executor.

    cross-request 정확히-1회는 라우터 try_claim이 보장한다(executor 내부 키는 approval_id 파생).
    idempotency_key는 감사/추적 + 향후 결과 replay 키로 전달·기록한다.
    """
    from api.routers.management import _get_executor
    executor: Executor = _get_executor()
    return await executor.execute(approved, proposal)


def _new_turn_id() -> str:
    return f"turn_{uuid4().hex[:12]}"  # 카드 trace id — thread/session id와 분리(§P2-3)


@router.post("/proposals/{proposal_id}/decision")
async def decide_proposal(
    proposal_id: str,
    body: DecisionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatCard:
    tenant_id, _ = await _resolve_tenant_account(user, db)  # execute 시점 authz
    store = ProposalStore(db)
    proposal = await store.get(proposal_id)
    turn_id = _new_turn_id()  # 카드 trace(분리). 이력 저장 thread는 body.thread_id 사용(Task8).

    if proposal is None or proposal.tenant_id != tenant_id:
        return _safe_expired(proposal_id, turn_id)  # 없거나 타 테넌트 — 추적 차단·안전 카드

    # reject — 멱등(PENDING→REJECTED 1회, 반복은 현재 상태)
    if body.decision == "reject":
        if proposal.status == ProposalStatus.PENDING:
            await store.set_status(proposal_id, ProposalStatus.REJECTED)
        return _terminal_card(proposal, "rejected", turn_id)

    # Tier3/chat-ineligible 서버 가드 — FE에만 기대지 않는다(§5.4). approve() 전에 즉시 차단.
    if requires_external_approval(proposal.action_tier):
        return _terminal_card(proposal, "rejected", turn_id)

    # 이미 실행 / 만료 가드
    if proposal.status == ProposalStatus.EXECUTED:
        return _terminal_card(proposal, "already_executed", turn_id)
    if proposal.expires_at < datetime.now(UTC):
        await store.set_status(proposal_id, ProposalStatus.EXPIRED)
        return _terminal_card(proposal, "expired", turn_id)

    # 원자적 claim — PENDING→APPROVED. 동시/중복은 정확히 1회만 통과(나머지는 already_executed).
    if not await store.try_claim(proposal_id):
        return _terminal_card(proposal, "already_executed", turn_id)

    # 서버 orchestration: approve()(정책 권위·4단계 재검증) → executor.execute()
    approved = approve(proposal, approver_id=str(getattr(user, "id", AUTO_APPROVER)),
                       execution_mode=_exec_mode())
    result = await _execute(approved, proposal, body.idempotency_key)
    rs = map_result_status(result.status, result.failure_reason)
    await store.set_status(
        proposal_id,
        ProposalStatus.EXECUTED if rs in ("success", "submitted_pending_review") else ProposalStatus.REJECTED,
    )
    return build_execution_result_card(proposal=proposal, result=result, run_id=None, turn_id=turn_id)


def _terminal_card(proposal, result_status: str, turn_id: str) -> ChatCard:
    return build_execution_result_card(proposal=proposal, result=None,
                                       run_id=None, turn_id=turn_id, result_status=result_status)


def _safe_expired(proposal_id: str, turn_id: str) -> ChatCard:
    """proposal이 없거나 타 테넌트 — 최소 안전 카드(정보 최소화)."""
    return ChatCard(
        type="management", status="neutral",
        sections=[ExecutionResultSection(
            title="집행 결과", action_type="UNKNOWN", result_status="expired",
            proposal_id=proposal_id, summary="제안을 찾을 수 없어요. 다시 검토를 요청해 주세요.",
        )],
        trace=TraceInfo(turn_id=turn_id),
    )


def _exec_mode():
    from api.routers.management import _resolved_execution_mode
    return _resolved_execution_mode()
```

> **정확히-1회 가드 정본은 `try_claim`(compare-and-set).** executor 내부 멱등(approval_id 파생)은 approve()마다 키가 달라 cross-request 보장이 약하고, `IdempotencyStore`도 인메모리다. 따라서 proposal_id 단위 원자적 전이로 동시·재시도 이중 집행을 막는다. `idempotency_key`는 `_execute`로 전달·기록(감사/추적)하되, executor 내부 변경(미수정 불변식)은 하지 않는다. 같은 클릭의 네트워크 재시도는 동일 key, 새 클릭은 새 key(§6) — claim 이후 재시도는 `already_executed`로 안전하게 닫힌다(이중 집행 없음).

- [ ] **Step 4: 통과 확인** → PASS (approve/expired/reject/중복키 4 테스트)
- [ ] **Step 5: 커밋**

```bash
git add backend/api/routers/chat_management.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: chat_management decision(approve/reject) + 가드·멱등 (스펙3)"
```

---

### Task 8: 라우터 등록 + 결과 카드 이력 적재·재조회

**Files:**
- Modify: `backend/api/main.py` (include_router append-only)
- Modify: `backend/api/routers/chat_management.py` (decision 끝에 결과 카드 적재)
- Modify: `backend/api/routers/chat.py` (`/sessions/{id}/messages` 스텁 → 저장 카드 역직렬화)
- Test: `backend/tests/management/test_chat_execution_bridge.py` (재조회 동일 렌더)

- [ ] **Step 1: main.py 등록** — 기존 include_router 블록 맨 끝에 1줄 추가(순서 유지):

```python
from api.routers import chat_management  # 상단 import 블록에
app.include_router(chat_management.router, prefix="/api/chat/management", tags=["chat-management"])
```

- [ ] **Step 2: 결과 카드 이력 적재** — decision이 카드를 반환하기 직전, `management_chat_messages`에 1건 적재(모든 terminal). chat_management.py에 헬퍼 추가:

```python
import json
from core.models import ManagementChatMessage

async def _persist_card(db: AsyncSession, thread_id: str, card: ChatCard) -> None:
    db.add(ManagementChatMessage(
        thread_id=thread_id, role="assistant",
        content=json.dumps(card.model_dump(mode="json"), ensure_ascii=False),
    ))
    await db.commit()
```

decision의 모든 `return ... card` 직전에 **`await _persist_card(db, body.thread_id or proposal_id, card)`** 호출(이력 저장 키는 **세션 thread_id**, 카드 trace의 `turn_id`와 분리 — §P2-3). 반환 지점이 여럿이므로 `decide_proposal`을 내부 함수로 카드 생성 → 단일 종료에서 persist+return하도록 묶는 게 깔끔하다.

- [ ] **Step 3: 재조회 역직렬화** — `chat.py`의 `get_session_messages` 스텁을 교체: thread_id로 `ManagementChatMessage`를 조회해, `content`가 카드 JSON이면 `{role, card}` 형태로 반환(역직렬화 실패 시 텍스트로 폴백).

```python
@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(
        select(ManagementChatMessage)
        .where(ManagementChatMessage.thread_id == session_id)
        .order_by(ManagementChatMessage.created_at)
    )).scalars().all()
    msgs = []
    for r in rows:
        card = None
        if r.content:
            try:
                parsed = json.loads(r.content)
                if isinstance(parsed, dict) and parsed.get("version") == 1:
                    card = parsed
            except (ValueError, TypeError):
                card = None
        msgs.append({"role": r.role, "content": None if card else r.content, "card": card})
    return {"session_id": session_id, "messages": msgs}
```

- [ ] **Step 4: 재조회 테스트** — decision 후 `GET /api/chat/sessions/{thread_id}/messages`가 동일 카드 JSON을 돌려주는지(라이브와 동일). 실행:

```python
@pytest.mark.asyncio
async def test_result_card_persisted_and_reloads_identically(db_session, monkeypatch):
    ...  # Task7 approve 흐름 재사용해 카드 받기
    async with AsyncClient(...) as ac:
        live = (await ac.post(".../decision", json={...})).json()
        reload = (await ac.get("/api/chat/sessions/mgmt-s1/messages")).json()
    assert reload["messages"][-1]["card"] == live
```

Run: `cd backend && uv run pytest tests/management/test_chat_execution_bridge.py -v`
Expected: PASS (전 게이트)

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/main.py backend/api/routers/chat_management.py backend/api/routers/chat.py backend/tests/management/test_chat_execution_bridge.py
git commit -m "add: chat_management 라우터 등록 + 결과 카드 이력 적재·재조회 (스펙3)"
```

---

## Phase C — 프론트엔드 (기존 카드 스타일, 필수 안전 상태)

> 프론트는 단위 테스트 하니스가 없으므로 각 태스크는 `pnpm lint` + `pnpm build` 통과 + 수동 확인으로 검증한다.

### Task 9: 타입 + API 클라이언트

**Files:**
- Modify: `frontend/src/lib/chatCard.ts`
- Create: `frontend/src/lib/managementActions.ts`

- [ ] **Step 1: `chatCard.ts` — `execution_result` 섹션 + proposal_id 추가**

`CardSection` union에 추가:

```ts
  | { kind: 'execution_result'; title?: string; action_type: string;
      result_status: 'success' | 'submitted_pending_review' | 'failed' | 'rejected' | 'expired' | 'already_executed';
      proposal_id: string; preview_id?: string; budget_before_krw?: number; budget_after_krw?: number;
      run_id?: string | null; summary: string; failure_reason?: string | null }
```

- [ ] **Step 2: `managementActions.ts` — finalize/decision fetch + idempotency 규칙**

```ts
// 챗 매니지먼트 집행 API — finalize(정본 승격)·decision(approve/reject). 정본 본문은 서버에만.
const API = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export type FinalizeResult = {
  status: 'finalized' | 'unavailable' | 'no_anomaly';
  proposal_id?: string; action_type?: string; tier?: string;
  requires_external_approval?: boolean;
  budget_before_krw?: number; budget_after_krw?: number;
  summary?: string; expires_at?: string; drift?: boolean; reason?: string;
};

export async function finalizeProposal(input: {
  previewId?: string; campaignId: string; threadId?: string; shownBudgetAfterKrw?: number;
}): Promise<FinalizeResult> {
  const res = await fetch(`${API}/api/chat/management/proposals/finalize`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      preview_id: input.previewId, campaign_id: input.campaignId, thread_id: input.threadId,
      shown_budget_after_krw: input.shownBudgetAfterKrw,
    }),
  });
  if (!res.ok) throw new Error(`finalize 실패 ${res.status}`);
  return res.json();
}

// idempotency_key: 한 클릭당 1개. 네트워크 재시도는 동일 key, 새 클릭은 새 key.
export function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

export async function decideProposal(input: {
  proposalId: string; decision: 'approve' | 'reject'; idempotencyKey: string; threadId?: string;
}): Promise<import('./chatCard').ChatCard> {
  const res = await fetch(`${API}/api/chat/management/proposals/${input.proposalId}/decision`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision: input.decision, idempotency_key: input.idempotencyKey, thread_id: input.threadId }),
  });
  if (!res.ok) throw new Error(`decision 실패 ${res.status}`);
  return res.json();
}
```

- [ ] **Step 3: lint/build** — `cd frontend && pnpm lint && pnpm build` → 통과
- [ ] **Step 4: 커밋**

```bash
git add frontend/src/lib/chatCard.ts frontend/src/lib/managementActions.ts
git commit -m "add: 프론트 execution_result 타입 + finalize/decision API 클라이언트 (스펙3)"
```

---

### Task 10: `execution_result` 렌더러

**Files:**
- Modify: `frontend/src/components/chat/sections.tsx`

- [ ] **Step 1: SECTION_RENDERERS에 `execution_result` 추가** (기존 스타일 토큰 재사용)

```tsx
  execution_result: (s) => {
    const tone: Record<string, string> = {
      success: 'text-[#15803D]', submitted_pending_review: 'text-[#B45309]',
      failed: 'text-[#DC2626]', rejected: 'text-[#8B95A1]',
      expired: 'text-[#8B95A1]', already_executed: 'text-[#8B95A1]',
    };
    return (
      <div>
        <Title title={s.title} />
        <p className={`text-sm font-semibold ${tone[s.result_status] ?? ''}`}>{s.summary}</p>
        {typeof s.budget_before_krw === 'number' && typeof s.budget_after_krw === 'number' && (
          <p className="text-xs text-[#4E5968] dark:text-[#9CA3AF] mt-0.5">
            예산 {s.budget_before_krw.toLocaleString()}원 → {s.budget_after_krw.toLocaleString()}원
          </p>
        )}
        {s.run_id && <p className="text-[11px] text-[#B0B8C1] mt-0.5">run · {s.run_id}</p>}
        {s.failure_reason && <p className="text-xs text-[#8B95A1] mt-0.5">{s.failure_reason}</p>}
      </div>
    );
  },
```

- [ ] **Step 2: lint/build** → 통과
- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/chat/sections.tsx
git commit -m "add: execution_result 섹션 렌더러 (스펙3)"
```

---

### Task 11: `ProposalActions` 상태 컴포넌트

**Files:**
- Create: `frontend/src/components/chat/ProposalActions.tsx`

상태 머신: `preview`(검토·승인 버튼) → `finalizing` → `finalized`(집행/거절 + TTL, drift면 "갱신값 확인" 1회) → `deciding` → 종결(결과 카드는 부모가 교체). `requires_external_approval`면 집행 대신 안내.

- [ ] **Step 1: 구현**

```tsx
// proposal 미리보기 카드의 안전 버튼 흐름 — finalize→approve/execute. 새 UX 표면 없음(필수 상태만).
'use client';
import { useState } from 'react';
import { decideProposal, finalizeProposal, newIdempotencyKey, type FinalizeResult } from '@/lib/managementActions';
import type { ChatCard } from '@/lib/chatCard';

type Props = {
  previewId?: string; campaignId: string; threadId?: string; shownBudgetAfterKrw?: number;
  onResult: (card: ChatCard) => void;   // 결과 카드로 교체
};

export default function ProposalActions({ previewId, campaignId, threadId, shownBudgetAfterKrw, onResult }: Props) {
  const [phase, setPhase] = useState<'preview' | 'finalizing' | 'finalized' | 'deciding'>('preview');
  const [fin, setFin] = useState<FinalizeResult | null>(null);
  const [driftAck, setDriftAck] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [idemKey, setIdemKey] = useState<string>('');

  async function onReview() {
    setPhase('finalizing'); setErr(null);
    try {
      const r = await finalizeProposal({ previewId, campaignId, threadId, shownBudgetAfterKrw });
      if (r.status !== 'finalized') { setErr(r.reason ?? '진단 결과가 없어요.'); setPhase('preview'); return; }
      setFin(r); setIdemKey(newIdempotencyKey()); setDriftAck(!r.drift); setPhase('finalized');
    } catch { setErr('요청 중 문제가 발생했어요.'); setPhase('preview'); }
  }

  async function onDecide(decision: 'approve' | 'reject') {
    if (!fin?.proposal_id) return;
    setPhase('deciding'); setErr(null);
    try {
      // 네트워크 재시도는 동일 idemKey(새 의도 아님). 새 클릭이 아니라 같은 클릭의 재시도.
      const card = await decideProposal({ proposalId: fin.proposal_id, decision, idempotencyKey: idemKey, threadId });
      onResult(card);
    } catch { setErr('집행 요청 중 문제가 발생했어요.'); setPhase('finalized'); }
  }

  if (phase === 'preview' || phase === 'finalizing') {
    return (
      <div className="mt-2">
        <button disabled={phase === 'finalizing'} onClick={onReview}
          className="px-3 py-1.5 text-xs rounded-md bg-[#3182F6] text-white disabled:opacity-50">
          {phase === 'finalizing' ? '준비 중…' : '검토·승인'}
        </button>
        {err && <p className="text-xs text-[#DC2626] mt-1">{err}</p>}
      </div>
    );
  }

  // finalized
  const expired = fin?.expires_at ? new Date(fin.expires_at).getTime() < Date.now() : false;
  if (fin?.requires_external_approval) {
    return <p className="mt-2 text-xs text-[#B45309]">정식 승인 화면에서 처리해야 하는 제안이에요.</p>;
  }
  return (
    <div className="mt-2 space-y-1">
      {fin?.drift && !driftAck && (
        <div className="text-xs text-[#B45309]">
          값이 갱신됐어요(집행 예산 {fin?.budget_after_krw?.toLocaleString()}원).
          <button onClick={() => setDriftAck(true)} className="ml-1 underline">갱신값 확인</button>
        </div>
      )}
      <div className="flex gap-2">
        <button disabled={phase === 'deciding' || expired || !driftAck} onClick={() => onDecide('approve')}
          className="px-3 py-1.5 text-xs rounded-md bg-[#3182F6] text-white disabled:opacity-50">
          {expired ? '만료됨' : phase === 'deciding' ? '집행 중…' : '집행'}
        </button>
        <button disabled={phase === 'deciding'} onClick={() => onDecide('reject')}
          className="px-3 py-1.5 text-xs rounded-md border border-[#E5E8EB] text-[#4E5968] disabled:opacity-50">
          거절
        </button>
      </div>
      {expired && <p className="text-xs text-[#8B95A1]">만료됐어요. 다시 검토를 요청해 주세요.</p>}
      {err && <p className="text-xs text-[#DC2626]">{err}</p>}
    </div>
  );
}
```

- [ ] **Step 2: lint/build** → 통과
- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/chat/ProposalActions.tsx
git commit -m "add: ProposalActions — finalize/decision 안전 상태 컴포넌트 (스펙3)"
```

---

### Task 12: ChatCardView에 연결

**Files:**
- Modify: `frontend/src/components/chat/ChatCardView.tsx`

- [ ] **Step 1: proposal 섹션(executable=false·preview_id 보유) 아래에 `ProposalActions`를 렌더**하고, `onResult`로 받은 결과 카드를 현재 카드의 섹션을 교체하거나 새 카드로 추가한다. `campaignId`/`threadId`는 ChatCardView가 받는 컨텍스트(현재 세션·context_ad/campaign)에서 전달한다. (proposal 섹션 렌더는 sections.tsx의 무상태 렌더러를 유지하고, 상호작용 레이어만 ChatCardView에서 proposal 섹션 옆에 끼운다.)

> 정확한 결선은 ChatCardView의 현재 구조(카드 상태 보관·섹션 순회 지점)에 맞춘다. 핵심 계약: ProposalActions에 `previewId=section.preview_id`, `campaignId`(세션 컨텍스트), `threadId=session_id`, `shownBudgetAfterKrw=section.budget_after_krw`를 넘기고, `onResult(card)`가 그 자리에서 결과 카드를 렌더하도록 한다.

- [ ] **Step 2: lint/build** → 통과
- [ ] **Step 3: 수동 확인** — `pnpm dev`로 매니지먼트 질문 → 이상 카드 → "검토·승인" → "집행" → 결과 카드 표시. 백엔드는 `use_mock=True`로 데모 경로.
- [ ] **Step 4: 커밋**

```bash
git add frontend/src/components/chat/ChatCardView.tsx
git commit -m "add: ChatCardView에 proposal 집행 흐름 연결 (스펙3)"
```

---

## Self-Review

**Spec coverage** — §3 흐름(finalize/decision)=Task6·7, §4 preview/proposal 경계=Task3·6(테스트 `proposal_id != preview_id`, preview_id trace=evidence_metrics→결과카드), §5.1 ExecutionResultSection=Task1, §5.2 FinalizeResult=Task2, §5.4 승인·Tier·external 영속=Task3·6·7(**Tier3 서버 가드 = decision에서 approve() 전 즉시 rejected**), §5.5 결과 source(ActionResult)=Task5·7, §6 idempotency=**Task4 `try_claim`(원자적 compare-and-set) 정본 + 병렬 10회 테스트(Task7)**·키 규칙(Task9), §7 FE 상태=Task9~12, §8 영속·재조회=Task8(이력=thread_id, 카드 trace=turn_id 분리), §9 테스트 게이트=Task별 테스트, §10 경계=미수정 파일(approval.py·executor.py·detection·ActionProposal) 손대지 않음.

**리뷰 반영(6건)** — (P1) idempotency_key를 `_execute`로 전달 + **정확히-1회는 `try_claim` 원자 전이**로 보장(executor 미수정), 병렬 중복 테스트 추가. (P1) Tier3/chat-ineligible **서버 가드**(FE 비의존). (P2) enum은 `.value`로 저장. (P2) `preview_id` trace를 evidence_metrics 경유로 결과 카드까지 전달. (P2) **thread_id(이력 저장)와 turn_id(카드 trace) 분리**.

**Placeholder scan** — `_safe_expired`/`_fake_user`/`db_session` 픽스처는 해당 태스크 Step에 구현 지침을 명시(추상 미완 아님). FE Task12는 ChatCardView 실제 구조에 맞춰 결선(계약은 고정).

**Type consistency** — `ExecutionResultSection`(BE models.py) ↔ `execution_result`(FE chatCard.ts) 필드 1:1. `FinalizeResult`(BE) ↔ `FinalizeResult`(FE) 키 일치(snake_case 응답). `map_result_status`/`build_execution_result_card`/`ProposalStore.get/save/set_status`/`build_action_proposal_from_diagnosis`/`requires_external_approval` 시그니처가 Task 간 일관.

**미해결 의존(실행 시 확인)** — `tests/management` conftest의 async DB 픽스처(`db_session`) 존재 여부. 없으면 Task4 Step1에서 추가(Neon 테스트 DB 또는 트랜잭션 롤백 픽스처). FE Task12는 ChatCardView 현재 코드 확인 후 결선.
