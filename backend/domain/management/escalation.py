"""🅱 시간축 자동 에스컬레이션 — 파괴도 낮은 조치부터 우선순위대로, 회복 안 되면 다음 단계.

`re_evaluate`는 전송 계층에 독립적인 순수 도메인 함수다(엔드포인트·데모 tick·추후 SQS consumer가
모두 같은 함수를 호출 → SQS-ready). 상태는 EscalationStore로 영속, 시각은 `now`로 주입(결정론·eval).

회복 판정 = `now` 시점 재탐지로 **원래 anomaly가 현재 anomaly 목록에 더 이상 없으면** 회복·멈춤
(top 진단 1건 동일성이 아니라 목록 멤버십). 여전히 남아 있으면 다음 단계로 에스컬레이션.

불변식 — Tier 3은 항상 건별 승인이므로 "자동"은 *다음 단계 제안의 자동 생성*만 뜻한다. 승인 없는
자동 집행은 없다(HITL 강제). 정보 방화벽: 진단 evidence + 구조화 입력만 읽는다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

from langsmith import traceable

from domain.management.agents.outcome import OutcomeKind
from domain.management.agents.regeneration import RemediationContext
from domain.management.contracts.enums import AnomalyType
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION, DAILY_BUDGET_KRW
from domain.management.execution.audit_log import AuditEvent

if TYPE_CHECKING:
    from datetime import datetime

    from domain.management.agents.regeneration import RemediationAgent
    from domain.management.contracts.schemas import ActionProposal, DiagnosisResult
    from domain.management.detection.service.detection_service import DetectionOutcome
    from domain.management.execution.audit_log import AuditSink

# ── 사다리 정의 (anomaly별 우선순위 action_type 목록) ──────────────────
# 모든 사다리의 마지막 칸은 CREATE_CAMPAIGN(재생성, 최후 수단).
# V1 = 기존 액션만 (바로 활성). V2 = 새 액션 사용 (등록 완료 후 ACTIVE_LADDERS에 합친다 — Phase 3).
LADDER_MATRIX_V1: dict[AnomalyType, list[str]] = {
    AnomalyType.QUALITY_DEGRADED: ["REPLACE_CREATIVE", "CREATE_CAMPAIGN"],
    AnomalyType.REVIEW_REJECTED: ["REPLACE_CREATIVE", "CREATE_CAMPAIGN"],
}
LADDER_MATRIX_V2: dict[AnomalyType, list[str]] = {
    AnomalyType.AUDIENCE_TOO_NARROW: ["EXPAND_AUDIENCE", "CHANGE_BID_STRATEGY", "CREATE_CAMPAIGN"],
    AnomalyType.BID_LOSS: ["CHANGE_BID_STRATEGY", "EXPAND_AUDIENCE", "CREATE_CAMPAIGN"],
}
#: 현재 활성 사다리 — Phase 3(새 액션 등록) 완료로 V1∪V2 활성.
#: EXPAND_AUDIENCE·CHANGE_BID_STRATEGY가 policy/executor/writer에 등록돼 제안 생성·집행 가능.
ACTIVE_LADDERS: dict[AnomalyType, list[str]] = {**LADDER_MATRIX_V1, **LADDER_MATRIX_V2}

#: 거절로 다음 단계가 제안될 때 카드에 노출할 안내 — 사용자가 "왜 또 생겼지?"로 느끼지 않게.
REJECTED_ESCALATION_NOTICE = (
    "이전 조치가 거절되어 다음 대안을 제안합니다. "
    "이 조치는 자동 실행되지 않으며 승인 후에만 집행됩니다."
)


def detected_anomalies(outcome: DetectionOutcome) -> set[AnomalyType]:
    """now 시점 anomaly 집합 — 단일 진단도 동작, 추후 복수 anomaly 구조로 자연 확장."""
    diagnoses = getattr(outcome, "diagnoses", None)
    if diagnoses:
        return {d.anomaly_type for d in diagnoses}
    if outcome.diagnosis is not None:
        return {outcome.diagnosis.anomaly_type}
    return set()


class EscalationStatus(StrEnum):
    NOOP = "noop"  # 사다리 대상 anomaly 없음 — 아무것도 안 함
    PENDING = "pending"  # 직전 단계 미결(승인/거절 대기) — 판정 보류
    ESCALATED = "escalated"  # 다음 단계 제안 생성 (reason 동반)
    RECOVERED = "recovered"  # 원래 anomaly 소멸 — 멈춤
    EXHAUSTED = "exhausted"  # 사다리 소진 — 더 올릴 단계 없음


@dataclass
class EscalationRun:
    """캠페인당 active 1건의 사다리 진행 상태 (인메모리)."""

    tenant_id: str
    ad_account_id: str
    campaign_id: str
    anomaly_type: str  # 사다리를 연 anomaly = 회복 판정 기준
    ladder: list[str]
    run_id: str = field(default_factory=lambda: f"esc_{uuid4().hex[:12]}")
    current_rung_index: int = 0
    rung_status: str = "proposed"  # proposed | executed | rejected
    rung_executed_at: datetime | None = None
    last_proposal_id: str | None = None
    last_approval_id: str | None = None
    status: str = "active"  # active | recovered | exhausted
    executed_count: int = 0
    opened_at: datetime | None = None
    last_evaluated_at: datetime | None = None


@dataclass(frozen=True)
class EscalationOutcome:
    status: EscalationStatus
    reason: str | None = None  # "opened" | "not_recovered" | "rejected"
    proposal: ActionProposal | None = None
    run_id: str | None = None
    notice: str | None = None  # 거절 에스컬레이션 카드 문구


class EscalationStore(Protocol):
    async def get_active(self, tenant_id: str, campaign_id: str) -> EscalationRun | None: ...

    async def get_by_run_id(self, run_id: str) -> EscalationRun | None: ...

    async def save(self, run: EscalationRun) -> None: ...


class AnomalyDetector(Protocol):
    """now 시점 재탐지 포트. executed_steps는 데모 시나리오 노브용(실연동은 무시)."""

    async def detect(
        self, tenant_id: str, campaign_id: str, *, now: datetime, executed_steps: int
    ) -> DetectionOutcome: ...


def default_context_factory(run: EscalationRun, action_type: str) -> RemediationContext:
    """사다리 단계 액션을 강제하는 실행 맥락 — 정책 기본값 + run 식별자 (라우터 패턴 미러)."""
    return RemediationContext(
        ad_account_id=run.ad_account_id,
        target_object_ids=(run.campaign_id,),
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        run_days=7,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        action_type=action_type,  # decide_action을 거치지 않고 이 단계 액션을 강제
    )


class EscalationController:
    """사다리 상태 머신 — open → (executed→회복판정 | rejected) → advance → recovered/exhausted."""

    def __init__(
        self,
        *,
        store: EscalationStore,
        detector: AnomalyDetector,
        agent: RemediationAgent,
        audit: AuditSink,
        ladders: dict[AnomalyType, list[str]] | None = None,
        context_factory=default_context_factory,
    ) -> None:
        self._store = store
        self._detector = detector
        self._agent = agent
        self._audit = audit
        self._ladders = ACTIVE_LADDERS if ladders is None else ladders
        self._context_factory = context_factory

    async def get_run(self, run_id: str) -> EscalationRun | None:
        """run_id로 사다리 run 조회 — 라우터의 tenant 소유 검증용(읽기 전용)."""
        return await self._store.get_by_run_id(run_id)

    @traceable(name="management.remediation", run_type="chain", tags=["management"])
    async def re_evaluate(
        self, tenant_id: str, ad_account_id: str, campaign_id: str, *, now: datetime
    ) -> EscalationOutcome:
        # 캠페인 평가 1회를 LangSmith 부모 트레이스로 묶는다 — 아래 진단(detect 내부)·재생성
        # (propose)이 자식 run으로 한 트리에 모인다. 트레이싱 꺼지면 무동작 통과.
        run = await self._store.get_active(tenant_id, campaign_id)
        outcome = await self._detector.detect(
            tenant_id,
            campaign_id,
            now=now,
            executed_steps=(run.executed_count if run else 0),
        )
        current = detected_anomalies(outcome)

        if run is None:  # 사다리 없음 — 활성 매트릭스에서 개시
            opener = next((a for a in current if a in self._ladders), None)
            if opener is None:
                return EscalationOutcome(EscalationStatus.NOOP)
            run = EscalationRun(
                tenant_id=tenant_id,
                ad_account_id=ad_account_id,
                campaign_id=campaign_id,
                anomaly_type=str(opener),
                ladder=list(self._ladders[opener]),
                opened_at=now,
                last_evaluated_at=now,
            )
            await self._log(run, "escalation.opened", {"anomaly": run.anomaly_type})
            return await self._propose_current(run, outcome.diagnosis, now, reason="opened")

        run.last_evaluated_at = now

        if run.rung_status == "proposed":  # 직전 단계 미결 → 판정 보류
            await self._store.save(run)
            return EscalationOutcome(EscalationStatus.PENDING, run_id=run.run_id)

        if run.rung_status == "rejected":  # 거절 → 회복 대기 없이 즉시 다음 단계
            return await self._advance(run, outcome.diagnosis, now, reason="rejected")

        # rung_status == "executed" → 회복 판정 (원래 anomaly가 현재 목록에 없으면 회복)
        if run.anomaly_type not in current:
            run.status = "recovered"
            await self._store.save(run)
            await self._log(run, "escalation.recovered", {"anomaly": run.anomaly_type})
            return EscalationOutcome(EscalationStatus.RECOVERED, run_id=run.run_id)
        return await self._advance(run, outcome.diagnosis, now, reason="not_recovered")

    # ── 집행/거절 전이 훅 (executor 성공 경로 / approval 거절 경로에서 호출) ──

    async def on_executed(
        self, run_id: str, *, now: datetime, approval_id: str | None = None
    ) -> None:
        run = await self._store.get_by_run_id(run_id)
        if run is None or run.status != "active":
            return
        run.rung_status = "executed"
        run.rung_executed_at = now
        run.executed_count += 1
        if approval_id is not None:
            run.last_approval_id = approval_id
        await self._store.save(run)

    async def on_rejected(self, run_id: str) -> None:
        run = await self._store.get_by_run_id(run_id)
        if run is None or run.status != "active":
            return
        run.rung_status = "rejected"
        await self._store.save(run)

    # ── 내부: 제안·전진 ────────────────────────────────────────────

    async def _propose_current(
        self, run: EscalationRun, diagnosis: DiagnosisResult | None, now: datetime, *, reason: str
    ) -> EscalationOutcome:
        """현재 단계 제안. 생성 실패(빈손)면 다음 단계로 전진."""
        proposal = await self._propose_rung(run, diagnosis)
        if proposal is None:
            return await self._advance(run, diagnosis, now, reason=reason)
        run.rung_status = "proposed"
        run.last_proposal_id = proposal.proposal_id
        await self._store.save(run)
        return self._escalated(run, reason, proposal)

    async def _advance(
        self, run: EscalationRun, diagnosis: DiagnosisResult | None, now: datetime, *, reason: str
    ) -> EscalationOutcome:
        """다음 단계로 올린다. 빈손 단계는 건너뛰고, 끝나면 EXHAUSTED."""
        while run.current_rung_index + 1 < len(run.ladder):
            prev_action = run.ladder[run.current_rung_index]
            run.current_rung_index += 1
            run.rung_status = "proposed"
            next_action = run.ladder[run.current_rung_index]
            await self._log(
                run,
                "escalation.advanced",
                {"reason": reason, "from_action": prev_action, "to_action": next_action},
            )
            proposal = await self._propose_rung(run, diagnosis)
            if proposal is not None:
                run.last_proposal_id = proposal.proposal_id
                await self._store.save(run)
                return self._escalated(run, reason, proposal)
            reason = "not_recovered"  # 빈손으로 건너뛴 뒤부터는 미회복 전진
        run.status = "exhausted"
        await self._store.save(run)
        await self._log(run, "escalation.exhausted", {"reason": reason})
        return EscalationOutcome(EscalationStatus.EXHAUSTED, reason=reason, run_id=run.run_id)

    async def _propose_rung(
        self, run: EscalationRun, diagnosis: DiagnosisResult | None
    ) -> ActionProposal | None:
        if diagnosis is None:  # 현재 anomaly 없음 → 처방할 대상 없음 (빈손)
            return None
        action_type = run.ladder[run.current_rung_index]
        context = self._context_factory(run, action_type)
        # 자동 사다리 예외 (스펙 §5d): 시간축 사다리는 단계 액션을 강제하고 자동 전진한다.
        # /regenerate 엔드포인트는 AWAITING_SELECTION을 사람에게 노출해 선택을 받지만,
        # 사다리는 비동기 시간축으로 운영되므로 최상위(4-3 idx 0) 후보를 자동 선택해
        # 즉시 package()한다. HITL 강제는 Tier-3 승인 단계(approval.py)에서 유지된다.
        outcome = await self._agent.rank(diagnosis, context)
        if outcome.kind is OutcomeKind.AWAITING_SELECTION:
            selected = outcome.candidates[0]["candidate_id"]
            outcome = await self._agent.package(
                outcome.selection_token,
                tenant_id=diagnosis.tenant_id,
                selected_id=selected,
            )
        if outcome.kind is OutcomeKind.PROPOSED:
            return outcome.proposal
        return None  # OBSERVE / CREATIVE_UNAVAILABLE / FAILED → 빈손(다음 단계 전진)

    def _escalated(
        self, run: EscalationRun, reason: str, proposal: ActionProposal
    ) -> EscalationOutcome:
        notice = REJECTED_ESCALATION_NOTICE if reason == "rejected" else None
        return EscalationOutcome(
            EscalationStatus.ESCALATED,
            reason=reason,
            proposal=proposal,
            run_id=run.run_id,
            notice=notice,
        )

    async def _log(self, run: EscalationRun, category: str, payload: dict) -> None:
        await self._audit.append(
            AuditEvent(
                category=category,
                tenant_id=run.tenant_id,
                proposal_id=run.last_proposal_id,
                approval_id=run.last_approval_id,
                run_id=run.run_id,
                payload={
                    "campaign_id": run.campaign_id,
                    "rung_index": run.current_rung_index,
                    **payload,
                },
            )
        )


class InMemoryEscalationStore:
    """인메모리 사다리 저장소 (use_mock·테스트). DB 구현(DbEscalationStore)과 교체 가능."""

    def __init__(self) -> None:
        self._runs: dict[str, EscalationRun] = {}

    async def get_active(self, tenant_id: str, campaign_id: str) -> EscalationRun | None:
        for run in self._runs.values():
            if (
                run.tenant_id == tenant_id
                and run.campaign_id == campaign_id
                and run.status == "active"
            ):
                return run
        return None

    async def get_by_run_id(self, run_id: str) -> EscalationRun | None:
        return self._runs.get(run_id)

    async def save(self, run: EscalationRun) -> None:
        self._runs[run.run_id] = run
