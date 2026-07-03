# panel sink 테스트 — 판정표(신규/미열람/쿨다운/후속/ignored)·race·reconcile·요약
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from domain.management.remediation.panel_sink import (
    KIND,
    DedupRaceError,
    PanelNotificationSink,
)


def _consult(status="anomaly", campaign_id="camp_1"):
    from domain.management.remediation.advisor import build_options
    from domain.management.remediation.contracts import ConsultResult

    return ConsultResult(
        status=status,
        campaign_id=campaign_id,
        campaign_name="여름 캠페인",
        anomaly_type="no_delivery" if status == "anomaly" else "",
        diagnosed_at=datetime.now(UTC).isoformat(),
        message="테스트 ①②",
        options=build_options("no_delivery") if status == "anomaly" else [],
    )


class Store:
    """알림 영속 포트 fake — open 상태·ignored 존재를 시나리오별로 주입."""

    def __init__(self, open_state=None, ignored=False, race=False):
        self._open = open_state  # None | {"id","read_at","last_notified_at"}
        self._ignored = ignored
        self._race = race
        self.inserted: list[dict] = []
        self.followups: list[tuple[str, dict]] = []
        self.auto_resolved: list[tuple] = []

    async def has_ignored(self, org_id, kind, dedup_key):
        return self._ignored

    async def open_state(self, org_id, kind, dedup_key):
        return self._open

    async def insert(self, **row):
        if self._race:
            raise DedupRaceError()
        self.inserted.append(row)
        return "notif-1"

    async def followup(self, notification_id, payload, now):
        self.followups.append((notification_id, payload))

    async def auto_resolve(self, org_id, kind, dedup_keys, now):
        self.auto_resolved.append((org_id, tuple(dedup_keys)))
        return ["org-9"] if dedup_keys else []


class FakeFallback:
    def __init__(self):
        self.calls = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.calls.append(tenant_id)


class _Settings:
    management_consult_cooldown_hours = 24


NOW = datetime.now(UTC)


def _sink(store, *, consult_result="anomaly", resolver_none=False, published=None):
    async def _resolver(campaign_id, *, expected_org_id=None):
        return None if resolver_none else ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        return None if consult_result == "fail" else _consult(status=consult_result)

    return PanelNotificationSink(
        _Settings(),
        fallback=FakeFallback(),
        store=store,
        resolver=_resolver,
        consult=_consult_fn,
        clock=lambda: NOW,
        publish=(published.append if published is not None else None),
    )


META = {"campaign_id": "camp_1", "anomaly_type": "no_delivery"}


@pytest.mark.asyncio
async def test_new_anomaly_inserts_and_publishes():
    store, published = Store(), []
    out = await _sink(store, published=published).deliver("t", "제목", "본문", meta=META)
    assert out.status == "delivered"
    row = store.inserted[0]
    assert row["dedup_key"] == "camp_1:no_delivery"
    assert row["kind"] == KIND
    assert row["payload"]["campaign_name"] == "여름 캠페인"  # 카드 표시용 확장 필드
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_ignored_skips_before_consult():
    calls = []

    async def counting_consult(settings, campaign_id, **kw):
        calls.append(1)
        return _consult()

    async def _resolver(campaign_id, *, expected_org_id=None):
        return ("proj-1", "org-9")

    sink = PanelNotificationSink(
        _Settings(),
        fallback=FakeFallback(),
        store=Store(ignored=True),
        resolver=_resolver,
        consult=counting_consult,
        clock=lambda: NOW,
    )
    out = await sink.deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "ignored"
    assert calls == []  # 판정 선행 — consult(reader I/O)를 안 탔다


@pytest.mark.asyncio
async def test_unread_open_row_skips_bell_pending():
    store = Store(open_state={"id": "n1", "read_at": None, "last_notified_at": NOW})
    out = await _sink(store).deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "bell_pending"


@pytest.mark.asyncio
async def test_read_within_cooldown_skips():
    state = {"id": "n1", "read_at": NOW, "last_notified_at": NOW - timedelta(hours=1)}
    out = await _sink(Store(open_state=state)).deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "cooldown"


@pytest.mark.asyncio
async def test_read_past_cooldown_followups():
    state = {"id": "n1", "read_at": NOW, "last_notified_at": NOW - timedelta(hours=25)}
    store, published = Store(open_state=state), []
    out = await _sink(store, published=published).deliver("t", "제목", "본문", meta=META)
    assert out.status == "delivered"
    assert store.followups and store.followups[0][0] == "n1"
    assert not store.inserted
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_dedup_race_skips():
    out = await _sink(Store(race=True)).deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "dedup_race"


@pytest.mark.asyncio
async def test_consult_normal_skips_verified_normal():
    out = await _sink(Store(), consult_result="normal").deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "verified_normal"


@pytest.mark.asyncio
async def test_followup_path_normal_closes_open_row():
    """열린 알림의 후속 경로에서 재검증이 정상이면 — skip에 그치지 않고 즉시 auto_normal."""
    state = {"id": "n1", "read_at": NOW, "last_notified_at": NOW - timedelta(hours=25)}
    store, published = Store(open_state=state), []
    out = await _sink(store, published=published, consult_result="normal").deliver(
        "t", "제목", "본문", meta=META
    )
    assert out.status == "skipped" and out.reason == "verified_normal"
    assert store.auto_resolved == [("org-9", ("camp_1:no_delivery",))]
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_no_hint_falls_back_to_consult_first():
    store = Store()
    out = await _sink(store).deliver("t", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    assert store.inserted[0]["dedup_key"] == "camp_1:no_delivery"  # consult 결과에서 유도


@pytest.mark.asyncio
async def test_no_mapping_skips_and_falls_back():
    fb = FakeFallback()
    sink = _sink(Store(), resolver_none=True)
    sink._fallback = fb
    out = await sink.deliver("t", "제목", "본문", meta=META)
    assert out.status == "skipped" and out.reason == "no_project_mapping"
    assert fb.calls  # 고정 스키마 폴백 로그 경로


@pytest.mark.asyncio
async def test_reconcile_auto_resolves_and_publishes():
    store, published = Store(), []
    sink = _sink(store, published=published)
    n = await sink.reconcile(
        [{"tenant_id": "org-9", "campaign_id": "camp_2", "anomaly_type": "no_delivery"}]
    )
    assert n == 1
    assert store.auto_resolved == [("org-9", ("camp_2:no_delivery",))]
    assert published == ["org-9"]


@pytest.mark.asyncio
async def test_summary_counts():
    store = Store()
    sink = _sink(store)
    await sink.deliver("t", "제목", "본문", meta=META)
    await sink.deliver("t", "제목", "본문", meta={})  # no_campaign_id
    s = sink.summary()
    assert s["delivered"] == 1
    assert s["skipped"][0]["reason"] == "no_campaign_id"
