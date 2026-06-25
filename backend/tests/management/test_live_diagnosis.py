# live_diagnosis 4-case + preview(정본 미생성) — mock reader로 앱·DB 없이
import pytest

from domain.management.adapters.mock import MockAdPlatform
from domain.management.assistant import tools as t
from domain.management.contracts.fault_injection import FaultConfig, FaultMode


class _Settings:
    use_mock = True


def _patch_reader(monkeypatch, reader):
    monkeypatch.setattr(t, "build_reader", lambda settings: reader)


@pytest.mark.asyncio
async def test_anomaly_returns_ok_anomaly_with_preview(monkeypatch):
    reader = MockAdPlatform(seed=1)
    orig = reader.fetch_hourly_metrics

    async def faulted(campaign_id, day, fault=None):
        return await orig(
            campaign_id, day, fault=FaultConfig(mode=FaultMode.BID_LOSS, probability=1.0)
        )

    monkeypatch.setattr(reader, "fetch_hourly_metrics", faulted)
    _patch_reader(monkeypatch, reader)

    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "ok"
    assert res.anomaly is True
    assert res.diagnosis is not None
    assert res.proposal_preview is not None
    assert res.proposal_preview.executable is False
    assert res.proposal_preview.preview_id.startswith("preview_")
    assert res.diagnosis.anomaly_type == "bid_loss"
    assert res.proposal_preview.action_type == "INCREASE_BUDGET"


@pytest.mark.asyncio
async def test_normal_returns_ok_no_anomaly(monkeypatch):
    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "ok"
    assert res.anomaly is False
    assert res.diagnosis is None


@pytest.mark.asyncio
async def test_insufficient_data_maps_to_unavailable(monkeypatch):
    from domain.management.detection.guardrails import GuardResult, GuardVerdict
    from domain.management.detection.service.detection_service import DetectionOutcome

    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    monkeypatch.setattr(
        t,
        "run_detection",
        lambda *a, **k: DetectionOutcome(
            GuardResult(GuardVerdict.INSUFFICIENT_DATA, reason="부족"), None, []
        ),
    )
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "unavailable"


@pytest.mark.asyncio
async def test_missing_campaign_returns_unavailable(monkeypatch):
    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    res = await t.live_diagnosis(_Settings(), "")
    assert res.diagnostic_status == "unavailable"
    assert res.reason


@pytest.mark.asyncio
async def test_real_mode_without_budget_is_unavailable(monkeypatch):
    class _Real:
        use_mock = False

    reader = MockAdPlatform(seed=1)
    _patch_reader(monkeypatch, reader)
    res = await t.live_diagnosis(_Real(), "camp_1")
    assert res.diagnostic_status == "unavailable"


@pytest.mark.asyncio
async def test_exception_returns_failed_without_raw(monkeypatch):
    class _Boom:
        async def fetch_hourly_metrics(self, campaign_id, day, fault=None):
            raise RuntimeError("SECRET reader down")

    _patch_reader(monkeypatch, _Boom())
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "failed"
    assert "SECRET" not in res.reason


def test_preview_builder_makes_no_canonical_proposal():
    from datetime import UTC, datetime

    from domain.management.contracts.enums import AnomalyType, DiagnosisSource, DiagnosisStatus
    from domain.management.contracts.schemas import DiagnosisResult

    dx = DiagnosisResult(
        diagnosis_id="dx1",
        tenant_id="org_eval",
        campaign_id="c1",
        anomaly_type=AnomalyType.BUDGET_EXHAUSTED,
        source=DiagnosisSource.DETERMINISTIC,
        hypothesis="예산 소진",
        confidence=1.0,
        evidence_metrics={},
        metrics_as_of=datetime.now(UTC),
        status=DiagnosisStatus.CONFIRMED,
    )
    preview = t.build_proposal_preview_from_diagnosis(dx, 100_000)
    assert preview.preview_id.startswith("preview_")
    assert preview.action_type == "INCREASE_BUDGET"
    assert preview.budget_before_krw == 100_000
    assert preview.executable is False and preview.persisted is False
    assert preview.source == "diagnostic_preview"
