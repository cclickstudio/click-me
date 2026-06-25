"""🅱 시간축 에스컬레이션 사다리 — open→escalate→recover / 소진 / 보류 / 거절→다음.

V1 사다리(기존 액션만: QUALITY_DEGRADED → REPLACE_CREATIVE → CREATE_CAMPAIGN)로 검증한다.
재탐지는 StepDetector로 결정론 주입(executed_steps 기준 회복) — 실 플랫폼·시간 대기 불필요.
"""

from types import SimpleNamespace

from domain.management.agents.regeneration import (
    CreativeCandidate,
    RemediationAgent,
)
from domain.management.contracts.enums import AnomalyType
from domain.management.contracts.schemas import DiagnosisResult
from domain.management.escalation import (
    REJECTED_ESCALATION_NOTICE,
    EscalationController,
    EscalationStatus,
    InMemoryEscalationStore,
)
from domain.management.execution.audit_log import InMemoryAuditLog
from tests.management.helpers import NOW

TENANT = "org-1111"
ACCOUNT = "act_001"
CAMPAIGN = "camp-001"


def make_diagnosis(anomaly=AnomalyType.QUALITY_DEGRADED) -> DiagnosisResult:
    return DiagnosisResult(
        diagnosis_id="diag-esc",
        tenant_id=TENANT,
        campaign_id=CAMPAIGN,
        anomaly_type=anomaly,
        source="agent",
        hypothesis="품질 저하 — 시안 피로도",
        confidence=0.7,
        evidence_metrics={"quality_ranking": "below_average_35"},
        metrics_as_of=NOW,
        status="confirmed",
    )


class StepDetector:
    """executed_steps가 recover_after에 도달하면 anomaly 소멸(=회복)로 보고."""

    def __init__(self, anomaly=AnomalyType.QUALITY_DEGRADED, recover_after: int | None = None):
        self.anomaly = anomaly
        self.recover_after = recover_after

    async def detect(self, tenant_id, campaign_id, *, now, executed_steps):
        if self.recover_after is not None and executed_steps >= self.recover_after:
            return SimpleNamespace(diagnosis=None)
        return SimpleNamespace(diagnosis=make_diagnosis(self.anomaly))


class StubGenerator:
    async def generate(self, diagnosis, count):
        # 새 시안(GENERATED_NEW) — guard asset 규칙을 위해 image_ref를 채운다.
        return [
            CreativeCandidate(
                candidate_id="c1", copy="여름맞이 신제품 출시", idx=0, image_ref="s3/new.png"
            )
        ]


def build_controller(detector):
    from domain.management.agents.selection import InMemorySelectionRoundStore

    # clock을 주입하지 않아 기본(real UTC)을 사용 — SelectionRound.expires_at이 항상 미래
    # (InMemorySelectionRoundStore.claim()이 real wall-clock으로 만료를 검증하므로).
    agent = RemediationAgent(
        generator=StubGenerator(),
        selection_store=InMemorySelectionRoundStore(),
    )
    audit = InMemoryAuditLog()
    controller = EscalationController(
        store=InMemoryEscalationStore(),
        detector=detector,
        agent=agent,
        audit=audit,
    )
    return controller, audit


async def test_open_escalate_then_recover():
    controller, audit = build_controller(StepDetector(recover_after=2))

    o0 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    assert o0.status is EscalationStatus.ESCALATED
    assert o0.reason == "opened"
    assert o0.proposal.action_type == "REPLACE_CREATIVE"  # 사다리 1순위(기존 액션)

    await controller.on_executed(o0.run_id, now=NOW)
    o1 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    assert o1.status is EscalationStatus.ESCALATED
    assert o1.reason == "not_recovered"
    assert o1.proposal.action_type == "CREATE_CAMPAIGN"  # 미회복 → 다음 단계(최후)

    await controller.on_executed(o1.run_id, now=NOW)
    o2 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    assert o2.status is EscalationStatus.RECOVERED  # anomaly 소멸 → 멈춤

    cats = {e.category for e in await audit.events()}
    assert {"escalation.opened", "escalation.advanced", "escalation.recovered"} <= cats


async def test_ladder_exhausts_when_never_recovers():
    controller, _ = build_controller(StepDetector(recover_after=None))

    o0 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    await controller.on_executed(o0.run_id, now=NOW)
    o1 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    await controller.on_executed(o1.run_id, now=NOW)
    o2 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)

    assert o2.status is EscalationStatus.EXHAUSTED  # 마지막 칸까지 집행 후 미회복


async def test_pending_when_rung_not_yet_resolved():
    controller, _ = build_controller(StepDetector(recover_after=None))

    o0 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    assert o0.status is EscalationStatus.ESCALATED  # 제안 생성(proposed)

    o1 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)  # 미집행·미거절
    assert o1.status is EscalationStatus.PENDING  # 판정 보류


async def test_rejected_escalates_immediately_with_notice():
    controller, _ = build_controller(StepDetector(recover_after=None))

    o0 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    assert o0.proposal.action_type == "REPLACE_CREATIVE"

    await controller.on_rejected(o0.run_id)
    o1 = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)

    assert o1.status is EscalationStatus.ESCALATED
    assert o1.reason == "rejected"  # 회복 대기 없이 즉시 다음 단계
    assert o1.proposal.action_type == "CREATE_CAMPAIGN"
    assert o1.notice == REJECTED_ESCALATION_NOTICE


async def test_noop_when_no_ladder_anomaly():
    # recover_after=0 → 첫 호출부터 anomaly 없음
    controller, _ = build_controller(StepDetector(recover_after=0))

    outcome = await controller.re_evaluate(TENANT, ACCOUNT, CAMPAIGN, now=NOW)
    assert outcome.status is EscalationStatus.NOOP


async def test_escalation_eval_v2_ladder_order_and_recovery():
    # 실 agent + 실 detection으로 V2 사다리(BID_LOSS, 새 액션 포함)를 시간축 관통.
    from domain.management.evals.regeneration_eval import run_escalation_eval

    report = await run_escalation_eval(recover_after=2)
    assert report.order_ok  # 사다리 우선순위대로 방문
    assert report.stopped_on_recovery  # 회복 시 정지
    # 새 액션이 실제로 제안·집행까지 도달
    assert report.visited_actions == ("CHANGE_BID_STRATEGY", "EXPAND_AUDIENCE")


async def test_escalation_eval_exhausts_without_recovery():
    from domain.management.evals.regeneration_eval import run_escalation_eval

    report = await run_escalation_eval(recover_after=99)  # 회복 없음
    assert report.terminal == "exhausted"
    assert report.visited_actions == ("CHANGE_BID_STRATEGY", "EXPAND_AUDIENCE", "CREATE_CAMPAIGN")
    assert report.order_ok


async def test_escalation_auto_picks_idx0_when_awaiting_selection():
    """FIX 2 — 사다리는 AWAITING_SELECTION 때 idx-0 후보를 자동 선택해 제안을 만든다(§5d 예외)."""
    from domain.management.agents.outcome import OutcomeKind, RemediationOutcome

    # AWAITING_SELECTION을 항상 반환하는 stub agent
    class _AwaitingAgent:
        _token = "tok-esc-auto"
        _candidate_id = "c-auto-0"

        async def rank(self, diagnosis, context):
            return RemediationOutcome(
                kind=OutcomeKind.AWAITING_SELECTION,
                selection_token=self._token,
                candidates=[{"candidate_id": self._candidate_id, "idx": 0, "copy": "테스트 카피"}],
            )

        async def package(self, selection_token, *, tenant_id, selected_id):
            assert selection_token == self._token
            assert selected_id == self._candidate_id
            # 실 proposal은 빌드하기 무거우므로 PROPOSED outcome을 직접 반환
            from uuid import uuid4

            from domain.management.contracts.enums import ActionTier, ProposalStatus
            from domain.management.contracts.schemas import ActionProposal, finalize_proposal
            from tests.management.helpers import NOW

            proposal = finalize_proposal(
                ActionProposal(
                    proposal_id=str(uuid4()),
                    tenant_id=tenant_id,
                    ad_account_id="act_esc_test",
                    target_object_ids=("camp_esc_test",),
                    action_type="REPLACE_CREATIVE",
                    action_tier=ActionTier.TIER_1,
                    evidence_metrics={"selected_candidate_id": selected_id},
                    metrics_as_of=NOW,
                    hypothesis="테스트",
                    confidence=0.8,
                    expected_state_version="sv1",
                    budget_before_krw=10_000,
                    budget_after_krw=10_000,
                    max_total_spend_krw=70_000,
                    expires_at=NOW,
                    approval_policy_version="v1",
                    status=ProposalStatus.PENDING,
                )
            )
            return RemediationOutcome(kind=OutcomeKind.PROPOSED, proposal=proposal)

    from types import SimpleNamespace

    from domain.management.contracts.enums import AnomalyType
    from domain.management.escalation import (
        ACTIVE_LADDERS,
        EscalationController,
        EscalationStatus,
        InMemoryEscalationStore,
    )
    from domain.management.execution.audit_log import InMemoryAuditLog
    from tests.management.helpers import NOW

    anomaly = AnomalyType.QUALITY_DEGRADED

    class _ConstDetector:
        async def detect(self, tenant_id, campaign_id, *, now, executed_steps):
            return SimpleNamespace(
                diagnosis=make_diagnosis(anomaly),
            )

    controller = EscalationController(
        store=InMemoryEscalationStore(),
        detector=_ConstDetector(),
        agent=_AwaitingAgent(),
        audit=InMemoryAuditLog(),
        ladders={anomaly: ACTIVE_LADDERS[anomaly]},
    )
    outcome = await controller.re_evaluate(TENANT, ACCOUNT, "camp-fix2", now=NOW)
    # 사다리가 AWAITING_SELECTION을 받아 자동 선택 → 제안 생성 → ESCALATED
    assert outcome.status is EscalationStatus.ESCALATED
    assert outcome.proposal is not None
    assert outcome.proposal.action_type == "REPLACE_CREATIVE"
