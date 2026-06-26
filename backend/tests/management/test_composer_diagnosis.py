# compose_card diagnostic 상태별 분기 + severity 파생
from domain.management.assistant.composer import compose_card, derive_severity
from domain.management.assistant.contracts import AskResult, DiagnosticResult


def _kinds(card):
    return [s.kind for s in card.sections]


def _ok_anomaly():
    return DiagnosticResult(
        diagnostic_status="ok",
        anomaly=True,
        diagnosis={
            "anomaly_type": "bid_loss",
            "status": "confirmed",
            "confidence": 1.0,
            "hypothesis": "입찰 패배",
        },
        proposal_preview={
            "preview_id": "preview_1",
            "action_type": "INCREASE_BUDGET",
            "campaign_id": "camp_1",
            "tier": "TIER_2",
            "budget_before_krw": 100000,
            "budget_after_krw": 150000,
            "hypothesis": "입찰 패배",
            "executable": False,
        },
    )


def test_severity_critical_for_confirmed_high_confidence():
    assert derive_severity(_ok_anomaly()) == "critical"


def test_severity_warning_for_confirmed_low_confidence():
    d = DiagnosticResult(
        diagnostic_status="ok",
        anomaly=True,
        diagnosis={
            "anomaly_type": "schedule_gap",
            "status": "confirmed",
            "confidence": 0.4,
            "hypothesis": "h",
        },
        proposal_preview={"preview_id": "p", "action_type": "REPLACE_CREATIVE"},
    )
    assert derive_severity(d) == "warning"


def test_severity_neutral_for_inconclusive_and_unavailable():
    inc = DiagnosticResult(
        diagnostic_status="ok",
        anomaly=True,
        diagnosis={
            "anomaly_type": "x",
            "status": "inconclusive",
            "confidence": 0.4,
            "hypothesis": "h",
        },
        proposal_preview={"preview_id": "p", "action_type": "REPLACE_CREATIVE"},
    )
    assert derive_severity(inc) == "neutral"
    assert (
        derive_severity(DiagnosticResult(diagnostic_status="unavailable", reason="r")) == "neutral"
    )


def test_ok_anomaly_builds_diagnosis_and_proposal_sections():
    card = compose_card(AskResult(answer="이상 감지", diagnostic=_ok_anomaly()), turn_id="t")
    assert "diagnosis" in _kinds(card)
    assert "proposal" in _kinds(card)
    assert card.status == "critical"
    proposal = next(s for s in card.sections if s.kind == "proposal")
    assert proposal.preview_id == "preview_1" and proposal.executable is False
    # 스펙3 — campaign_id가 proposal 섹션까지 스레딩된다(FE finalize 결선용).
    assert proposal.campaign_id == "camp_1"


def test_ok_no_anomaly_summary_metrics_only():
    card = compose_card(
        AskResult(
            answer="정상입니다.",
            evidence={"this_month_spent_krw": 100},
            diagnostic=DiagnosticResult(diagnostic_status="ok", anomaly=False),
        ),
        turn_id="t",
    )
    assert "diagnosis" not in _kinds(card)
    assert card.status == "neutral"


def test_unavailable_renders_empty_state_neutral():
    card = compose_card(
        AskResult(
            answer="진단 시도",
            diagnostic=DiagnosticResult(diagnostic_status="unavailable", reason="데이터 없음"),
        ),
        turn_id="t",
    )
    assert "empty_state" in _kinds(card)
    assert card.status == "neutral"


def test_failed_renders_empty_state_neutral():
    card = compose_card(
        AskResult(
            answer="진단 시도",
            diagnostic=DiagnosticResult(diagnostic_status="failed", reason="툴 오류"),
        ),
        turn_id="t",
    )
    assert "empty_state" in _kinds(card)


def test_no_diagnostic_keeps_v0_path():
    card = compose_card(
        AskResult(answer="일반 답변", evidence={"this_month_spent_krw": 100}), turn_id="t"
    )
    assert _kinds(card) == ["summary", "metrics"]
    assert card.status is None
