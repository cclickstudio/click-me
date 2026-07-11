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
import contextlib
import hashlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Final, Protocol
from uuid import uuid4

from domain.management.contracts.approval_ledger import ApprovalStore, record_mismatches
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
    CampaignConfig,
    verify_proposal_hash,
)
from domain.management.execution.audit_log import AuditEvent, AuditSink
from domain.management.execution.state_machine import ExecutionRun, RunStatus
from domain.management.execution.tier import (
    BudgetAuthority,
    BudgetDecision,
    estimate_max_total_spend,
)

#: v1 executor가 실행 가능한 action_type — 어휘 정본은 contracts/policy.py TIER_POLICY (P1)
#: REPLACE_CREATIVE는 replace_creative_tree로 실행 — 소재 필드 + 결속 affected_ad_ids 기반 fan-out.
#: 그 밖의 미등록 action_type은 Writer 도달 전 UNSUPPORTED_ACTION으로 차단.
SUPPORTED_ACTION_TYPES: Final[tuple[str, ...]] = (
    "PAUSE_CAMPAIGN",
    "DECREASE_BUDGET",
    "INCREASE_BUDGET",
    "REPLACE_CREATIVE",
    "CREATE_CAMPAIGN",  # PR2 — 신규 캠페인 생성 (config는 evidence_metrics에 적재, 옵션 A)
    "ACTIVATE_CAMPAIGN",  # 게재 시작 — 캠페인·광고세트·광고 전부 ACTIVE (크레딧 게이트 후 호출)
    "EXPAND_AUDIENCE",  # 에스컬레이션 사다리 1순위 — 타겟 범위 확장 (direct)
    "CHANGE_BID_STRATEGY",  # 에스컬레이션 사다리 2순위 — 입찰 전략 변경 (direct)
    "REBALANCE_BUDGET",  # Tier 2 — 캠페인 간 일예산 이전(총액 불변), 전용 경로 _call_rebalance
)

#: Writer 도달이 허용되는 실행 모드 (기본). LIVE는 기본 불허 —
#: _get_executor가 use_mock=False + mode=live일 때만 명시적으로 append(opt-in)한다.
#: ⚠️ LIVE는 실제 게재·실과금이라 기본 executor 게이트에서 EXECUTION_MODE_DISABLED로 막힌다.
DEFAULT_ALLOWED_MODES: Final[tuple[ExecutionMode, ...]] = (
    ExecutionMode.MOCK,
    ExecutionMode.DRY_RUN,
    ExecutionMode.VALIDATE_ONLY,
)

#: 지출을 증가시키는 액션 — max_total_spend_krw를 클라이언트 신고값이 아닌 서버 재계산값으로 방어.
_SPEND_INCREASING_ACTIONS: Final[frozenset[str]] = frozenset(
    {"INCREASE_BUDGET", "ACTIVATE_CAMPAIGN", "CREATE_CAMPAIGN"}
)
#: _build_budget_proposal·demo와 동일 산정일수 — estimate_max_total_spend 재계산 기준.
_DEFAULT_RUN_DAYS: Final[int] = 7


def build_idempotency_key(action: ApprovedAction, proposal: ActionProposal) -> str:
    """P5 멱등키 산식 [안]: hash(approval_id + action_type + target_object_ids)."""
    raw = "|".join([action.approval_id, proposal.action_type, *sorted(proposal.target_object_ids)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class IdempotencyStore(Protocol):
    """DB ``idempotency_keys.key UNIQUE + INSERT ... ON CONFLICT DO NOTHING`` 대응 Port.

    메서드는 async (DB 구현 DbIdempotencyStore와 교체 가능). reserve는 테이블
    ``approval_id`` NOT NULL 충족을 위해 approval_id를 함께 받는다.
    """

    async def reserve(self, key: str, approval_id: str) -> bool: ...

    async def get_result(self, key: str) -> ActionResult | None: ...

    async def save_result(self, key: str, result: ActionResult) -> None: ...

    async def release(self, key: str) -> None: ...


class InMemoryIdempotencyStore:
    """인메모리 멱등 저장소 — DB 구현(DbIdempotencyStore)으로 교체 가능."""

    def __init__(self) -> None:
        self._reserved: set[str] = set()
        self._results: dict[str, ActionResult] = {}

    async def reserve(self, key: str, approval_id: str) -> bool:
        if key in self._reserved:
            return False
        self._reserved.add(key)
        return True

    async def get_result(self, key: str) -> ActionResult | None:
        return self._results.get(key)

    async def save_result(self, key: str, result: ActionResult) -> None:
        self._results[key] = result

    async def release(self, key: str) -> None:
        # 결과 없이 선점만 한 상태를 푼다 — 일시 실패 후 재승인 없이 재시도 가능하게.
        self._reserved.discard(key)


#: ad_account_id → 현재 state_version 조회 (낙관적 락 비교의 우변)
StateVersionProvider = Callable[[str], Awaitable[str]]

#: 실행 성공을 롱텀 메모리(실행 히스토리)에 남기는 콜백 — 구현은 history_link(wiring 주입)
HistoryRecorder = Callable[["ApprovedAction", "ActionProposal", "ActionResult"], Awaitable[None]]


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
        history_recorder: HistoryRecorder | None = None,  # None=기록 생략(테스트·미배선)
        # 승인 원장(게이트 #5) — 기본값 없음(필수). None은 의도적 생략 명시(데모 CLI 등).
        approvals: ApprovalStore | None,
    ) -> None:
        self._writer = writer
        self._history_recorder = history_recorder
        self._approvals = approvals
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
            return await self._reject(run, action, proposal, reason, detail)

        # 4.5) 승인 원장 대조 (게이트 #5) — 서버가 발행하지 않은(위조) 승인 차단.
        # _validate()는 sync 순수 함수로 유지하고 원장 조회(async)만 여기서 한다(스펙 §3.3).
        ledger_rejection = await self._verify_approval_record(action)
        if ledger_rejection is not None:
            reason, detail = ledger_rejection
            return await self._reject(run, action, proposal, reason, detail)

        # 5) expected_state_version 비교 — 낙관적 락
        current_version = await self._state_version_provider(proposal.ad_account_id)
        if current_version != action.expected_state_version:
            return await self._reject(
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
        replayed = await self._idempotency.get_result(key)
        if replayed is not None:
            await self._record(
                run,
                action,
                proposal,
                "executor.duplicate_suppressed",
                {"idempotency_key": key, "replayed": True},
            )
            return replayed

        budget = self._budget_for(action.tenant_id)
        # 지출 증가 액션은 클라이언트 신고값을 신뢰하지 않고 서버 재계산값으로 예산 평가·커밋한다.
        effective = self._effective_spend(proposal)
        decision = budget.evaluate(effective)
        if decision is BudgetDecision.BLOCK:
            return await self._reject(
                run, action, proposal, FailureReason.BUDGET_CAP_EXCEEDED, "100% 하드캡 차단"
            )
        if decision is BudgetDecision.ESCALATE and action.approver_id == AUTO_APPROVER:
            return await self._reject(
                run,
                action,
                proposal,
                FailureReason.BUDGET_CAP_EXCEEDED,
                "95% 소프트캡 — 자율(AUTO) 불가, 사용자 승인 라우팅 필요 (P4)",
            )
        if decision is BudgetDecision.WARN:
            await self._record(run, action, proposal, "executor.softcap_warn", {"threshold": "90%"})

        if not await self._idempotency.reserve(key, action.approval_id):
            # 선점됐는데 결과가 없다 = 동시 요청이 호출 진행 중 (in-flight)
            await self._record(
                run,
                action,
                proposal,
                "executor.duplicate_suppressed",
                {"idempotency_key": key, "replayed": False},
            )
            return await self._reject(
                run, action, proposal, FailureReason.PLATFORM_ERROR, "멱등키 선점됨(in-flight)"
            )
        run.advance(RunStatus.RESERVED)

        # 7) Writer 호출 (재시도·부분 실패 포함) + 감사 기록
        run.advance(RunStatus.CALLING)
        result = await self._call_targets(run, action, proposal, key)
        if result.status in (ResultStatus.SUCCESS, ResultStatus.SUBMITTED_PENDING_REVIEW):
            await self._idempotency.save_result(key, result)
            budget.commit(effective)
            if self._approvals is not None:
                with contextlib.suppress(Exception):  # 마킹 실패가 실행 결과를 바꾸지 않게
                    await self._approvals.consume(action.approval_id, self._clock())
        elif result.failure_reason is FailureReason.PARTIAL_FAILURE:
            # 일부 타깃은 이미 집행됨 — 자동 재시도 시 성공분 중복 집행 위험이라 결과를
            # 박제(재생)하고 사람이 개입한다(P5/게이트 #7). 집행된 비율만큼만 예산 권한을
            # 커밋해 잔여 권한이 과대 계상(하드캡 약화)되지 않게 한다.
            await self._idempotency.save_result(key, result)
            executed = self._executed_target_count(result)
            total = len(proposal.target_object_ids) or 1
            if executed:
                budget.commit(effective * executed // total)
        else:
            # 아무 타깃도 집행되지 않은 일시 실패 — 멱등 선점을 풀어 재승인 없이 재시도 가능.
            await self._idempotency.release(key)
        await self._record(
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
        # 실행 확정을 롱텀 메모리(실행 히스토리)에 기록 — 신규 성공분만(재생·거부 제외).
        # 기록 실패가 실행 결과를 바꾸지 않게 삼킨다(best-effort).
        if self._history_recorder is not None and result.status in (
            ResultStatus.SUCCESS,
            ResultStatus.SUBMITTED_PENDING_REVIEW,
        ):
            with contextlib.suppress(Exception):
                await self._history_recorder(action, proposal, result)
        return result

    # ── 4)단계 검증 ──────────────────────────────────────────────

    async def _verify_approval_record(
        self, action: ApprovedAction
    ) -> tuple[FailureReason, str] | None:
        """게이트 #5 — 제출된 ApprovedAction을 서버 승인 원장과 대조한다.

        consumed_at으로는 거부하지 않는다(관측·감사용) — 재제출 차단은 멱등 게이트 담당.
        """
        if self._approvals is None:
            return None
        record = await self._approvals.get(action.approval_id)
        if record is None:
            return FailureReason.UNAPPROVED_ACTION, "승인 원장에 없는 approval_id (게이트 #5)"
        mismatched = record_mismatches(record, action)
        if mismatched:
            return (
                FailureReason.UNAPPROVED_ACTION,
                f"승인 원장 불일치: {', '.join(mismatched)} (게이트 #5)",
            )
        return None

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
        if action.action_tier is ActionTier.TIER_2 and action.approver_id == AUTO_APPROVER:
            return FailureReason.INVALID_TIER, "Tier 2는 건별 사용자 승인 필수 (자율 실행 비활성)"
        if action.action_tier is ActionTier.TIER_3 and action.approver_id == AUTO_APPROVER:
            return FailureReason.UNAPPROVED_ACTION, "Tier 3은 건별 사용자 승인 필수 (게이트 #4)"
        # 레거시 REPLACE(selected_candidate_id·campaign target)는 Meta ad/creative 모델과 안 맞아
        # 실 모드(validate/live)에서 캠페인 id를 ad로 보내 승인 후 Meta에서 깨진다(codex 리뷰 high).
        # → mock 데모는 허용하되 실 모드는 승인 전 fail-fast 거부(신규 affected_ad_ids 계약 필요).
        em = proposal.evidence_metrics
        legacy_replace = (
            proposal.action_type == "REPLACE_CREATIVE"
            and "affected_ad_ids" not in em
            and "selected_candidate_id" in em
        )
        if legacy_replace and action.execution_mode in (
            ExecutionMode.VALIDATE_ONLY,
            ExecutionMode.LIVE,
        ):
            return (
                FailureReason.UNSUPPORTED_ACTION,
                "레거시 selected_candidate_id REPLACE는 mock 전용(실 모드는 신규 계약 필요)",
            )
        return None

    # ── 7)단계 Writer 호출 ───────────────────────────────────────

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
                    await self._record(
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

    async def _call_rebalance(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        key: str,
    ) -> ActionResult:
        """REBALANCE_BUDGET 전용 — 감액(from)→증액(to), 증액 실패 시 감액 원복(보상) 1회.

        총예산이 순간적으로도 늘지 않게 감액이 먼저다. 보상 성공=순변경 0(비-PARTIAL,
        멱등 해제로 같은 승인 TTL 내 재시도 가능), 보상 실패=PARTIAL_FAILURE(박제 —
        P5/게이트 #7, 같은 승인 재집행 차단 + 수동 복구 안내).
        """

        def _invalid(detail: str) -> ActionResult:
            run.advance(RunStatus.FAILED)
            return self._build_result(
                action,
                key,
                ResultStatus.FAILED,
                FailureReason.UNSUPPORTED_ACTION,
                [{"error": f"REBALANCE_BUDGET 계약 위반: {detail}"}],
            )

        em = proposal.evidence_metrics
        targets = proposal.target_object_ids
        try:
            from_before = int(em["from_before_krw"])
            from_after = int(em["from_after_krw"])
            to_before = int(em["to_before_krw"])
            to_after = int(em["to_after_krw"])
            move = int(em["move_krw"])
        except (KeyError, TypeError, ValueError):
            return _invalid("evidence_metrics 필드 누락/불량")
        # 최종 게이트 불변식 — 타깃 정확히 2개·상이, 감액분=증액분=move>0
        # (총액 불변은 두 등식에서 자동 도출).
        if len(targets) != 2 or targets[0] == targets[1]:
            return _invalid("from/to 타깃은 서로 다른 2개여야 함")
        if move <= 0 or from_before - from_after != move or to_after - to_before != move:
            return _invalid("이동량 불일치 (감액분=증액분=move 위반)")
        from_id, to_id = targets[0], targets[1]

        snapshots: list[dict[str, Any]] = []

        async def _leg(target: str, amount: int, suffix: str) -> ActionResult:
            # leg 키는 감사 식별자일 뿐 dedup 키가 아니다 — 보상 성공 후 같은 승인 재시도가
            # 동일 dec 키를 재사용하므로, writer/플랫폼이 이 키로 dedup하면 감액이 no-op되어
            # 총액 불변이 깨진다. 액션 단위 멱등은 execute()의 키가 담당한다.
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
        if dec.status is not ResultStatus.SUCCESS:
            # SUBMITTED_PENDING_REVIEW 등 불확정 — 적용 여부를 몰라 진행·보상 모두 불가.
            return await self._halt_indeterminate(run, action, proposal, key, snapshots)
        run.record_snapshot(snapshots[-1])

        inc = await _leg(to_id, to_after, "inc")
        if inc.status is ResultStatus.SUCCESS:
            run.record_snapshot(snapshots[-1])
            run.advance(RunStatus.SUCCEEDED)
            return self._build_result(action, key, ResultStatus.SUCCESS, None, snapshots)
        if inc.status is not ResultStatus.FAILED:
            # 불확정 증액 — 나중에 적용될 수 있어 원복(보상)하면 이중 변경 위험. 박제.
            return await self._halt_indeterminate(run, action, proposal, key, snapshots)
        if inc.failure_reason is FailureReason.TIMEOUT:
            # 타임아웃은 '적용됐는데 응답만 유실'일 수 있다(적대 리뷰) — 이때 보상하면
            # 증액·원복이 둘 다 남아 총예산이 부푼다. 확정 실패가 아니므로 보상 없이 박제.
            return await self._halt_indeterminate(run, action, proposal, key, snapshots)

        comp = await _leg(from_id, from_before, "comp")
        if comp.status is ResultStatus.SUCCESS:
            # 원복 완료 — 순변경 0. 비-PARTIAL이라 멱등키가 해제돼 같은 승인 TTL 내 재시도 가능.
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

        # 보상 실패·불확정 — 부분 변경 방치 상태. 박제(재집행 차단) + 수동 복구 안내.
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

    async def _halt_indeterminate(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        key: str,
        snapshots: list[dict[str, Any]],
    ) -> ActionResult:
        """다리 결과가 성공도 실패도 아닌 불확정(pending 등) — 진행·보상 없이 박제.

        재시도하면 불확정 다리가 이중 적용될 수 있어 PARTIAL_FAILURE로 봉인하고 사람이 본다.
        (현 adjust_budget writer는 success/failed만 반환 — executor 계약 방어용.)
        """
        snapshots.append({"indeterminate": True})
        run.advance(RunStatus.HALTED, snapshot=snapshots[-1])
        await self._record(
            run,
            action,
            proposal,
            "executor.partial_failure",
            {"indeterminate": True, "snapshots": snapshots},
        )
        return self._build_result(
            action, key, ResultStatus.FAILED, FailureReason.PARTIAL_FAILURE, snapshots
        )

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
            await self._record(
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
        if proposal.action_type == "REPLACE_CREATIVE":
            em = proposal.evidence_metrics
            # 경로 판별(코드리뷰 #5) — 신규 명시-후보 계약은 affected_ad_ids로 식별(엔드포인트가
            # 항상 결속). 없고 selected_candidate_id만 있으면 레거시 재생성 단건 교체.
            # image_hash 유무에 결합하지 않아, 레거시가 image_hash를 실어도 안전.
            if "affected_ad_ids" not in em and "selected_candidate_id" in em:
                creative_id = em.get("selected_candidate_id")
                if not creative_id:
                    raise ValueError("REPLACE_CREATIVE 제안에 selected_candidate_id 없음")
                return await self._writer.replace_creative(target, str(creative_id), idem_key)
            image_hash = em.get("image_hash")
            headline = em.get("headline")
            body = em.get("body")
            link_url = em.get("link_url")
            ad_ids = em.get("affected_ad_ids")
            # 빌드 단계가 항상 채우는 필드 — 없으면 계약 위반(_validate 통과분 방어).
            # image_hash 필수(텍스트-only 불허). 결속된 광고로만 fan-out → 프리뷰=집행 대상 결속.
            if not image_hash or not headline or not body or not link_url:
                raise ValueError(
                    "REPLACE_CREATIVE 제안 소재 필드 누락(image_hash/headline/body/link_url)"
                )
            # 타입 방어(리뷰 P2-a) — 문자열이 들어오면 글자 단위 fan-out되므로 명시 검증.
            if (
                not isinstance(ad_ids, (list, tuple))
                or not ad_ids
                or not all(isinstance(a, str) and a for a in ad_ids)
            ):
                raise ValueError("affected_ad_ids는 비어있지 않은 문자열 리스트여야 함")
            return await self._writer.replace_creative_tree(
                target,  # 캠페인 id(멱등 키 정체성) — fan-out 대상은 결속된 ad_ids
                ad_ids=[str(a) for a in ad_ids],
                ad_account_id=proposal.ad_account_id,
                image_hash=str(image_hash),
                headline=str(headline),
                body=str(body),
                link_url=str(link_url),
                idem_key=idem_key,
            )
        if proposal.action_type == "CREATE_CAMPAIGN":
            # 옵션 A — 신규 캠페인은 대상 id가 없어 config를 evidence_metrics로 받는다.
            raw = proposal.evidence_metrics.get("campaign_config")
            if not raw:
                raise ValueError("CREATE_CAMPAIGN 제안에 campaign_config 없음")
            config = raw if isinstance(raw, CampaignConfig) else CampaignConfig(**raw)
            # 오케스트레이션 — 캠페인→광고세트→(리드면 폼→광고)를 한 흐름으로. page_id는
            # writer가 .env(META_PAGE_ID)에서 채운다. 검증 모드면 캠페인 단계까지만 동작.
            return await self._writer.create_full_campaign(config, idem_key)
        if proposal.action_type == "ACTIVATE_CAMPAIGN":
            # 게재 시작 — 캠페인·광고세트·광고를 전부 ACTIVE로(한 단계라도 PAUSED면 미게재).
            return await self._writer.activate_tree(target, idem_key)
        if proposal.action_type == "EXPAND_AUDIENCE":
            return await self._writer.expand_audience(target, idem_key)
        if proposal.action_type == "CHANGE_BID_STRATEGY":
            return await self._writer.change_bid_strategy(target, idem_key)
        raise ValueError(f"미지원 action_type: {proposal.action_type}")  # _validate에서 차단됨

    # ── 결과·감사 헬퍼 ───────────────────────────────────────────

    @staticmethod
    def _effective_spend(proposal: ActionProposal) -> int:
        """지출 증가 액션은 클라이언트 신고값을 신뢰하지 않고 budget_after로 서버 재계산(하한).

        위조 제안이 max_total_spend_krw=0으로 예산 하드캡을 우회하는 것을 막는다.
        REBALANCE_BUDGET/DECREASE_BUDGET 등 총액 불변·감소 액션은 신고값 유지.
        """
        if proposal.action_type in _SPEND_INCREASING_ACTIONS:
            return max(
                proposal.max_total_spend_krw,
                estimate_max_total_spend(proposal.budget_after_krw, _DEFAULT_RUN_DAYS),
            )
        return proposal.max_total_spend_krw

    @staticmethod
    def _executed_target_count(result: ActionResult) -> int:
        """부분 실패 결과에서 실제 집행(성공/심사보류)된 타깃 수 — 비례 예산 커밋용."""
        snaps = (result.platform_response_snapshot or {}).get("targets") or []
        done = {str(ResultStatus.SUCCESS), str(ResultStatus.SUBMITTED_PENDING_REVIEW)}
        return sum(1 for s in snaps if s.get("status") in done)

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

    async def _reject(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        reason: FailureReason,
        detail: str,
    ) -> ActionResult:
        if not run.is_terminal:
            run.advance(RunStatus.FAILED)
        await self._record(
            run, action, proposal, "executor.rejected", {"reason": reason, "detail": detail}
        )
        return self._build_result(
            action, build_idempotency_key(action, proposal), ResultStatus.REJECTED, reason, None
        )

    async def _record(
        self,
        run: ExecutionRun,
        action: ApprovedAction,
        proposal: ActionProposal,
        category: str,
        payload: dict[str, Any],
    ) -> None:
        await self._audit.append(
            AuditEvent(
                category=category,
                tenant_id=action.tenant_id,
                proposal_id=proposal.proposal_id,
                approval_id=action.approval_id,
                run_id=run.run_id,
                payload=payload,
            )
        )
