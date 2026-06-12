"""🅱 executor — 승인 후 4단계(4~7) 재검증 + 멱등 실행. 모든 지출의 단일 경로 (§4).

승인 전 3단계는 approval.py(🅰)의 책임이지만, 여기의 재검증은 의도적 중복
(defense in depth) — 승인~실행 사이의 시간 갭 동안 상황 변경을 잡는다.
어느 쪽도 "저쪽이 하니까"로 생략하지 않는다 (불변 규칙 §4-4).

    4) ApprovedAction 유효성 재확인 (만료·정책버전·hash·tenant·Tier)
    5) expected_state_version 비교 — 불일치 = STALE_PROPOSAL → 새 제안
    6) 지출 후 총액 재계산 → 멱등키 선점 후 호출
    7) 응답·후속조회 감사 로그 기록 (재시도·부분 실패 포함)
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from uuid import uuid4

from domain.management.contracts.enums import (
    ActionTier,
    ExecutionMode,
    FailureReason,
    ResultStatus,
)
from domain.management.contracts.platform import AdPlatformWriter
from domain.management.contracts.schemas import (
    AUTO_APPROVER,
    ActionProposal,
    ActionResult,
    ApprovedAction,
    verify_proposal_hash,
)
from domain.management.execution.audit_log import AuditEvent, AuditSink
from domain.management.execution.state_machine import ExecutionRun, RunStatus
from domain.management.execution.tier import BudgetAuthority, BudgetDecision

#: v1 executor가 실행 가능한 action_type — 어휘 정본은 contracts/policy.py TIER_POLICY (P1)
#: REPLACE_CREATIVE 등은 Port(D8)에 메서드가 없어 v1 실행 불가 → UNSUPPORTED_ACTION
SUPPORTED_ACTION_TYPES: Final[tuple[str, ...]] = (
    "PAUSE_CAMPAIGN",
    "DECREASE_BUDGET",
    "INCREASE_BUDGET",
)

#: v1에서 Writer 도달이 허용되는 실행 모드 — LIVE는 비활성 (§7 Must)
DEFAULT_ALLOWED_MODES: Final[tuple[ExecutionMode, ...]] = (
    ExecutionMode.MOCK,
    ExecutionMode.DRY_RUN,
    ExecutionMode.SANDBOX_CONTRACT,
)


def build_idempotency_key(action: ApprovedAction, proposal: ActionProposal) -> str:
    """P5 멱등키 산식 [안]: hash(approval_id + action_type + target_object_ids)."""
    raw = "|".join([action.approval_id, proposal.action_type, *sorted(proposal.target_object_ids)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyStore(Protocol):
    """DB ``idempotency_keys.key UNIQUE + INSERT ... ON CONFLICT DO NOTHING`` 대응 Port."""

    def reserve(self, key: str) -> bool: ...

    def get_result(self, key: str) -> ActionResult | None: ...

    def save_result(self, key: str, result: ActionResult) -> None: ...


class InMemoryIdempotencyStore:
    """인메모리 멱등 저장소 — core 테이블 합의 후 DB 구현으로 교체."""

    def __init__(self) -> None:
        self._reserved: set[str] = set()
        self._results: dict[str, ActionResult] = {}

    def reserve(self, key: str) -> bool:
        if key in self._reserved:
            return False
        self._reserved.add(key)
        return True

    def get_result(self, key: str) -> ActionResult | None:
        return self._results.get(key)

    def save_result(self, key: str, result: ActionResult) -> None:
        self._results[key] = result


#: ad_account_id → 현재 state_version 조회 (낙관적 락 비교의 우변)
StateVersionProvider = Callable[[str], Awaitable[str]]


class Executor:
    """지출 단일 경로 — agent·서비스의 Writer 직접 호출은 금지 (불변 규칙 §4-1)."""

    def __init__(
        self,
        writer: AdPlatformWriter,
        *,
        idempotency: IdempotencyStore,
        audit: AuditSink,
        budget_for: Callable[[str], BudgetAuthority],  # tenant_id → 예산 권한 (멀티테넌트)
        state_version_provider: StateVersionProvider,
        current_policy_version: str,
        allowed_modes: tuple[ExecutionMode, ...] = DEFAULT_ALLOWED_MODES,
        timeout_max_retries: int = 2,  # P5 [안]: WRITE_TIMEOUT 최대 2회, 지수 백오프
        rate_limit_max_retries: int = 1,  # P5 [안]: RATE_LIMITED 대기 후 1회
        backoff_base_seconds: float = 0.05,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._writer = writer
        self._idempotency = idempotency
        self._audit = audit
        self._budget_for = budget_for
        self._state_version_provider = state_version_provider
        self._current_policy_version = current_policy_version
        self._allowed_modes = allowed_modes
        self._timeout_max_retries = timeout_max_retries
        self._rate_limit_max_retries = rate_limit_max_retries
        self._backoff_base_seconds = backoff_base_seconds
        self._clock = clock
        self._sleep = sleep

    async def execute(self, action: ApprovedAction, proposal: ActionProposal) -> ActionResult:
        run = ExecutionRun(approval_id=action.approval_id)

        # 4) ApprovedAction 유효성 재확인
        rejection = self._validate(action, proposal)
        if rejection is not None:
            reason, detail = rejection
            return self._reject(run, action, proposal, reason, detail)

        # 5) expected_state_version 비교 — 낙관적 락
        current_version = await self._state_version_provider(proposal.ad_account_id)
        if current_version != action.expected_state_version:
            return self._reject(
                run,
                action,
                proposal,
                FailureReason.STALE_PROPOSAL,
                f"state_version 불일치: expected={action.expected_state_version}, "
                f"current={current_version}",
            )
        run.advance(RunStatus.VALIDATED)

        # 6) 멱등 재생 → 지출 후 총액 재계산 → 소프트캡 판정 → 멱등키 선점
        # 완료된 중복 제출은 예산 평가 전에 기존 결과를 재생한다 — 재생이 예산을
        # 두 번 소모하면 게이트 #1(같은 키 = 실행 1건)이 잔액 한도에서 깨진다.
        key = build_idempotency_key(action, proposal)
        replayed = self._idempotency.get_result(key)
        if replayed is not None:
            self._record(
                run,
                action,
                proposal,
                "executor.duplicate_suppressed",
                {"idempotency_key": key, "replayed": True},
            )
            return replayed

        budget = self._budget_for(action.tenant_id)
        decision = budget.evaluate(proposal.max_total_spend_krw)
        if decision is BudgetDecision.BLOCK:
            return self._reject(
                run, action, proposal, FailureReason.BUDGET_CAP_EXCEEDED, "100% 하드캡 차단"
            )
        if decision is BudgetDecision.ESCALATE and action.approver_id == AUTO_APPROVER:
            return self._reject(
                run,
                action,
                proposal,
                FailureReason.BUDGET_CAP_EXCEEDED,
                "95% 소프트캡 — 자율(AUTO) 불가, 사용자 승인 라우팅 필요 (P4)",
            )
        if decision is BudgetDecision.WARN:
            self._record(run, action, proposal, "executor.softcap_warn", {"threshold": "90%"})

        if not self._idempotency.reserve(key):
            # 선점됐는데 결과가 없다 = 동시 요청이 호출 진행 중 (in-flight)
            self._record(
                run,
                action,
                proposal,
                "executor.duplicate_suppressed",
                {"idempotency_key": key, "replayed": False},
            )
            return self._reject(
                run, action, proposal, FailureReason.PLATFORM_ERROR, "멱등키 선점됨(in-flight)"
            )
        run.advance(RunStatus.RESERVED)

        # 7) Writer 호출 (재시도·부분 실패 포함) + 감사 기록
        run.advance(RunStatus.CALLING)
        result = await self._call_targets(run, action, proposal, key)
        self._idempotency.save_result(key, result)
        if result.status in (ResultStatus.SUCCESS, ResultStatus.SUBMITTED_PENDING_REVIEW):
            budget.commit(proposal.max_total_spend_krw)
        self._record(
            run,
            action,
            proposal,
            "executor.completed",
            {
                "status": result.status,
                "failure_reason": result.failure_reason,
                "idempotency_key": key,
                "attempts": run.attempts,
            },
        )
        return result

    # ── 4)단계 검증 ──────────────────────────────────────────────

    def _validate(
        self, action: ApprovedAction, proposal: ActionProposal
    ) -> tuple[FailureReason, str] | None:
        now = self._clock()
        if action.execution_mode not in self._allowed_modes:
            return FailureReason.EXECUTION_MODE_DISABLED, f"{action.execution_mode} 비활성 (v1)"
        if now >= action.expires_at:
            return FailureReason.APPROVAL_EXPIRED, "승인 만료 — 재승인 필요"
        if now >= proposal.expires_at:
            return FailureReason.PROPOSAL_EXPIRED, "제안 TTL 만료 (게이트 #2)"
        if action.approval_policy_version != self._current_policy_version:
            return FailureReason.STALE_PROPOSAL, "approval_policy_version 불일치 → 새 제안 (P2)"
        if action.tenant_id != proposal.tenant_id:
            return FailureReason.TENANT_MISMATCH, "tenant 불일치 (게이트 #3 이중검증)"
        if action.proposal_id != proposal.proposal_id:
            return FailureReason.PROPOSAL_HASH_MISMATCH, "proposal_id 불일치"
        if action.proposal_hash != proposal.proposal_hash or not verify_proposal_hash(proposal):
            return FailureReason.PROPOSAL_HASH_MISMATCH, "제안 변조 감지"
        if proposal.action_type not in SUPPORTED_ACTION_TYPES:
            return FailureReason.UNSUPPORTED_ACTION, f"미지원 action_type: {proposal.action_type}"
        if action.action_tier is ActionTier.TIER_2:
            return FailureReason.INVALID_TIER, "Tier 2 자동 실행은 v1 비활성"
        if action.action_tier is ActionTier.TIER_3 and action.approver_id == AUTO_APPROVER:
            return FailureReason.UNAPPROVED_ACTION, "Tier 3은 건별 사용자 승인 필수 (게이트 #4)"
        return None

    # ── 7)단계 Writer 호출 ───────────────────────────────────────

    async def _call_targets(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        key: str,
    ) -> ActionResult:
        snapshots: list[dict[str, Any]] = []
        pending = False
        for index, target in enumerate(proposal.target_object_ids):
            outcome = await self._call_with_retry(run, action, proposal, target, f"{key}:{target}")
            snapshots.append(
                {
                    "target": target,
                    "status": str(outcome.status),
                    "failure_reason": outcome.failure_reason,
                    "response": outcome.platform_response_snapshot,
                }
            )
            if outcome.status is ResultStatus.FAILED:
                if index > 0:
                    # 부분 실패 — 스냅샷 기록 후 정지, 자동 롤백 없음 (P5 → 게이트 #7)
                    run.advance(RunStatus.HALTED, snapshot=snapshots[-1])
                    self._record(
                        run,
                        action,
                        proposal,
                        "executor.partial_failure",
                        {"succeeded": index, "failed_target": target, "snapshots": snapshots},
                    )
                    return self._build_result(
                        action, key, ResultStatus.FAILED, FailureReason.PARTIAL_FAILURE, snapshots
                    )
                run.advance(RunStatus.FAILED, snapshot=snapshots[-1])
                return self._build_result(
                    action,
                    key,
                    ResultStatus.FAILED,
                    outcome.failure_reason or FailureReason.PLATFORM_ERROR,
                    snapshots,
                )
            run.record_snapshot(snapshots[-1])
            if outcome.status is ResultStatus.SUBMITTED_PENDING_REVIEW:
                pending = True

        if pending:
            run.advance(RunStatus.PENDING_REVIEW)
            return self._build_result(
                action, key, ResultStatus.SUBMITTED_PENDING_REVIEW, None, snapshots
            )
        run.advance(RunStatus.SUCCEEDED)
        return self._build_result(action, key, ResultStatus.SUCCESS, None, snapshots)

    async def _call_with_retry(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        target: str,
        idem_key: str,
    ) -> ActionResult:
        timeout_attempts = 0
        rate_attempts = 0
        while True:
            run.record_attempt()
            try:
                outcome = await self._dispatch(proposal, target, idem_key)
            except TimeoutError:
                outcome = self._build_result(
                    action, idem_key, ResultStatus.FAILED, FailureReason.TIMEOUT, None
                )
            except Exception as exc:  # noqa: BLE001 — 어댑터 경계: 모든 예외를 결과로 변환
                outcome = self._build_result(
                    action,
                    idem_key,
                    ResultStatus.FAILED,
                    FailureReason.PLATFORM_ERROR,
                    [{"error": str(exc)}],
                )
            if outcome.status is not ResultStatus.FAILED:
                return outcome

            if (
                outcome.failure_reason is FailureReason.TIMEOUT
                and timeout_attempts < self._timeout_max_retries
            ):
                timeout_attempts += 1
                delay = self._backoff_base_seconds * (2 ** (timeout_attempts - 1))
            elif (
                outcome.failure_reason is FailureReason.RATE_LIMITED
                and rate_attempts < self._rate_limit_max_retries
            ):
                rate_attempts += 1
                delay = self._backoff_base_seconds
            else:
                return outcome
            self._record(
                run,
                action,
                proposal,
                "executor.retry",
                {"target": target, "reason": outcome.failure_reason, "delay_s": delay},
            )
            await self._sleep(delay)

    async def _dispatch(self, proposal: ActionProposal, target: str, idem_key: str) -> ActionResult:
        if proposal.action_type == "PAUSE_CAMPAIGN":
            return await self._writer.pause(target, idem_key)
        if proposal.action_type in ("DECREASE_BUDGET", "INCREASE_BUDGET"):
            return await self._writer.adjust_budget(target, proposal.budget_after_krw, idem_key)
        raise ValueError(f"미지원 action_type: {proposal.action_type}")  # _validate에서 차단됨

    # ── 결과·감사 헬퍼 ───────────────────────────────────────────

    def _build_result(
        self,
        action: ApprovedAction,
        idem_key: str,
        status: ResultStatus,
        failure_reason: FailureReason | None,
        snapshots: list[dict[str, Any]] | None,
    ) -> ActionResult:
        return ActionResult(
            result_id=str(uuid4()),
            approval_id=action.approval_id,
            status=status,
            failure_reason=failure_reason,
            platform_response_snapshot={"targets": snapshots} if snapshots else None,
            executed_at=self._clock(),
            idempotency_key=idem_key,
        )

    def _reject(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        reason: FailureReason,
        detail: str,
    ) -> ActionResult:
        if not run.is_terminal:
            run.advance(RunStatus.FAILED)
        self._record(
            run, action, proposal, "executor.rejected", {"reason": reason, "detail": detail}
        )
        return self._build_result(
            action, build_idempotency_key(action, proposal), ResultStatus.REJECTED, reason, None
        )

    def _record(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        category: str,
        payload: dict[str, Any],
    ) -> None:
        self._audit.append(
            AuditEvent(
                category=category,
                tenant_id=action.tenant_id,
                proposal_id=proposal.proposal_id,
                approval_id=action.approval_id,
                run_id=run.run_id,
                payload=payload,
            )
        )
