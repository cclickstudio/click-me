# live_diagnosis 4-case + preview(정본 미생성) — mock reader로 앱·DB 없이
import pytest

from domain.management.adapters.mock import MockAdPlatform
from domain.management.assistant import tools as t
from domain.management.contracts.fault_injection import FaultConfig, FaultMode


class _Settings:
    use_mock = True


def _patch_reader(monkeypatch, reader):
    monkeypatch.setattr(t, "build_reader", lambda settings: reader)


class _FakeRealReader:
    """실측 모드용 결정적 reader — list_campaigns(예산)·fetch_hourly_metrics(스냅샷) 주입."""

    def __init__(self, campaigns, snapshots):
        self._campaigns = campaigns
        self._snapshots = snapshots

    async def list_campaigns(self, include_archived=False):
        return self._campaigns

    async def fetch_hourly_metrics(self, campaign_id, day):
        return self._snapshots


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


class _Real:
    use_mock = False


@pytest.mark.asyncio
async def test_real_mode_without_campaign_budget_is_unavailable(monkeypatch):
    # 실측 모드인데 캠페인을 못 찾으면(또는 일예산 없음) 합성 금지 → unavailable.
    _patch_reader(monkeypatch, _FakeRealReader(campaigns=[], snapshots=[]))
    res = await t.live_diagnosis(_Real(), "camp_1")
    assert res.diagnostic_status == "unavailable"


@pytest.mark.asyncio
async def test_real_mode_with_campaign_budget_reaches_detection(monkeypatch):
    # 실측 모드라도 캠페인 daily_budget을 소싱하면 진단을 수행한다(unavailable로 막히지 않음).
    from datetime import UTC, datetime

    from domain.management.contracts.enums import CampaignState
    from domain.management.contracts.schemas import CampaignInfo

    snapshots = await MockAdPlatform(seed=1).fetch_hourly_metrics("camp_1", datetime.now(UTC))
    campaign = CampaignInfo(
        campaign_id="camp_1",
        name="C",
        state=CampaignState.ACTIVE,
        daily_budget_krw=200_000,
        budget_type="daily",
    )
    _patch_reader(monkeypatch, _FakeRealReader(campaigns=[campaign], snapshots=snapshots))
    res = await t.live_diagnosis(_Real(), "camp_1")
    # 핵심: 실측 모드라도 일예산을 소싱해 진단을 수행한다(unavailable로 막히지 않음).
    assert res.diagnostic_status == "ok"


@pytest.mark.asyncio
async def test_exception_returns_failed_without_raw(monkeypatch):
    class _Boom:
        async def fetch_hourly_metrics(self, campaign_id, day, fault=None):
            raise RuntimeError("SECRET reader down")

    _patch_reader(monkeypatch, _Boom())
    res = await t.live_diagnosis(_Settings(), "camp_1")
    assert res.diagnostic_status == "failed"
    assert "SECRET" not in res.reason


def test_hour_aligned_snapshots_fills_gaps_by_clock_hour():
    # detection이 snapshots[h]를 시각 인덱스로 읽으므로 빈 시각은 0으로 채워 위치=시각을 보장.
    from datetime import UTC, datetime

    from domain.management.contracts.schemas import MetricsSnapshot

    def snap(h, impr):
        return MetricsSnapshot(
            campaign_id="c",
            as_of=datetime(2026, 6, 25, h, 0, tzinfo=UTC),
            impressions=impr,
            clicks=0,
            inline_link_clicks=0,
            spend_krw=0,
            cum_impressions=impr,
            cum_reach=0,
            frequency=0.0,
            ctr=0.0,
            cpm_krw=0,
            cpc_krw=0,
        )

    out = t._hour_aligned_snapshots([snap(0, 10), snap(2, 30)], "c")
    assert [s.impressions for s in out] == [10, 0, 30]  # 시각 1은 0 노출로 채움
    assert out[1].as_of.hour == 1
    assert t._hour_aligned_snapshots([], "c") == []


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
