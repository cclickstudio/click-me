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
        return [CreativeCandidate(candidate_id="c1", ad_copy="여름맞이 신제품 출시")]


class StubScorer:
    async def score(self, candidate):
        return 0.9


def build_controller(detector):
    agent = RemediationAgent(generator=StubGenerator(), scorer=StubScorer(), clock=lambda: NOW)
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
