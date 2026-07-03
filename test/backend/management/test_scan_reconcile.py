# run_scan 확장 테스트 — (findings, normals) 튜플 스캐너 + reconcile 호출·구형 스캐너 호환
from __future__ import annotations

import pytest

from domain.management.scheduler import run_scan


class SinkSpy:
    def __init__(self):
        self.notified, self.reconciled = [], []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.notified.append(meta)

    async def reconcile(self, normals):
        self.reconciled.append(normals)
        return len(normals)


class PlainSink:  # reconcile 없는 기존 sink (LogNotificationSink 상당)
    def __init__(self):
        self.notified = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.notified.append(meta)


@pytest.mark.asyncio
async def test_tuple_scanner_delivers_and_reconciles():
    async def scanner(_s):
        findings = [{"tenant_id": "org-1", "title": "t", "body": "b",
                     "meta": {"campaign_id": "c1", "anomaly_type": "no_delivery"}}]
        normals = [{"tenant_id": "org-1", "campaign_id": "c2", "anomaly_type": "no_delivery"}]
        return findings, normals

    sink = SinkSpy()
    n = await run_scan(object(), sink, scanner=scanner)
    assert n == 1
    assert sink.notified[0]["anomaly_type"] == "no_delivery"
    assert sink.reconciled == [[{"tenant_id": "org-1", "campaign_id": "c2",
                                 "anomaly_type": "no_delivery"}]]


@pytest.mark.asyncio
async def test_legacy_list_scanner_still_works():
    async def scanner(_s):
        return [{"tenant_id": "g", "title": "t", "body": "b", "meta": {"campaign_id": "c1"}}]

    sink = PlainSink()
    assert await run_scan(object(), sink, scanner=scanner) == 1


@pytest.mark.asyncio
async def test_normals_without_reconcile_capable_sink_is_noop():
    async def scanner(_s):
        return [], [{"tenant_id": "g", "campaign_id": "c2", "anomaly_type": "no_delivery"}]

    sink = PlainSink()
    assert await run_scan(object(), sink, scanner=scanner) == 0  # 예외 없이 무시


@pytest.mark.asyncio
async def test_manual_scan_uses_panel_sink_when_channel_is_panel(monkeypatch):
    # 수동 스캔 엔드포인트가 management_notify_channel="panel"일 때 PanelNotificationSink를
    # 생성하는지 — sink 생성부는 함수 내부 seam이라 PanelNotificationSink 클래스를 스파이로 교체.
    import asyncio

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from api.routers import management as mgmt
    from core.auth import get_current_user
    from core.config import settings
    from domain.management.remediation import panel_sink as panel_sink_mod
    from domain.management.remediation.chat_sink import DeliveryOutcome

    created: dict = {}

    class SpyPanelSink:
        def __init__(self, *args, **kwargs):
            created["called"] = True
            created["kwargs"] = kwargs

        async def deliver(self, *args, **kwargs):
            return DeliveryOutcome(campaign_id="camp_x", status="delivered")

        def summary(self):
            return {"delivered": 1, "skipped": [], "failed": []}

    async def fake_run_scan(_settings, sink, *, scanner=None):
        await asyncio.sleep(0)
        out = await sink.deliver("org-1", "제목", "본문", meta={"campaign_id": "camp_x"})
        return 1 if out.status == "delivered" else 0

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr(settings, "management_notify_channel", "panel", raising=False)
    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 0, raising=False)
    monkeypatch.setattr(panel_sink_mod, "PanelNotificationSink", SpyPanelSink)
    monkeypatch.setattr("domain.management.scheduler.run_scan", fake_run_scan)
    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    mgmt._notify_scan_locks.clear()
    mgmt._notify_scan_last.clear()

    application = FastAPI()
    application.include_router(mgmt.router, prefix="/api/management")
    application.dependency_overrides[get_current_user] = lambda: object()

    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.post("/api/management/anomaly/notify-scan")

    assert r.status_code == 200
    assert created.get("called") is True
