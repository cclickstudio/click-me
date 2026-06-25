# DiagnosticResult 4-case validator + 중첩 typed 모델(ProposalPreview/DiagnosisView) — 불법 조합/값 거부  # noqa: E501
import pytest
from pydantic import ValidationError

from domain.management.assistant.contracts import (
    AskResult,
    DiagnosisView,
    DiagnosticResult,
    ProposalPreview,
)


def _view():
    return DiagnosisView(
        anomaly_type="bid_loss", status="confirmed", confidence=1.0, hypothesis="입찰 패배"
    )


def _preview():
    return ProposalPreview(
        preview_id="preview_1",
        action_type="INCREASE_BUDGET",
        budget_before_krw=100,
        budget_after_krw=150,
    )


def test_ok_anomaly_requires_diagnosis_and_proposal():
    d = DiagnosticResult(
        diagnostic_status="ok", anomaly=True, diagnosis=_view(), proposal_preview=_preview()
    )
    assert d.anomaly is True


def test_ok_anomaly_without_proposal_rejected():
    with pytest.raises(ValidationError):
        DiagnosticResult(
            diagnostic_status="ok", anomaly=True, diagnosis=_view(), proposal_preview=None
        )


def test_ok_anomaly_without_diagnosis_rejected():
    with pytest.raises(ValidationError):
        DiagnosticResult(
            diagnostic_status="ok", anomaly=True, diagnosis=None, proposal_preview=_preview()
        )


def test_ok_no_anomaly_forbids_payload():
    ok = DiagnosticResult(diagnostic_status="ok", anomaly=False)
    assert ok.diagnosis is None and ok.proposal_preview is None
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="ok", anomaly=False, proposal_preview=_preview())


def test_unavailable_forbids_payload_requires_reason():
    u = DiagnosticResult(diagnostic_status="unavailable", reason="데이터 없음")
    assert u.diagnosis is None and u.anomaly is False
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="unavailable", reason="")
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="unavailable", reason="x", diagnosis=_view())


def test_failed_requires_reason():
    f = DiagnosticResult(diagnostic_status="failed", reason="툴 오류")
    assert f.proposal_preview is None
    with pytest.raises(ValidationError):
        DiagnosticResult(diagnostic_status="failed", reason="")


def test_proposal_preview_locks_safety_invariants():
    # executable=True·proposal_id·임의 키는 타입/extra=forbid로 거부(정본/실행 가능 오인 차단)
    with pytest.raises(ValidationError):
        ProposalPreview(preview_id="p", action_type="X", executable=True)
    with pytest.raises(ValidationError):
        ProposalPreview(preview_id="p", action_type="X", proposal_id="prop_1")
    pv = _preview()
    assert pv.executable is False and pv.finalized is False and pv.persisted is False


def test_askresult_diagnostic_optional_default_none():
    assert AskResult(answer="x").diagnostic is None
