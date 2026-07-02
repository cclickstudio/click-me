# 수동 알림 스캔 엔드포인트 테스트 — 동시 409·쿨다운 429·실패 재시도·배달 요약 응답
from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app(monkeypatch):
    from fastapi import FastAPI

    from api.routers import management as mgmt
    from core.auth import get_current_user
    from core.config import settings

    # 느린 스캔을 흉내내 동시성 창을 만든다 + org 해석·요약만 검증
    async def fake_run_scan(_settings, sink, *, scanner=None):
        await asyncio.sleep(0.05)
        out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_x"})
        return 1 if out.status == "delivered" else 0

    async def fake_require_org_id(user, db):
        return "org-1"

    monkeypatch.setattr("domain.management.scheduler.run_scan", fake_run_scan)
    monkeypatch.setattr(mgmt, "_require_org_id", fake_require_org_id)
    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 0, raising=False)
    # 잠금·쿨다운 전역 상태 초기화(테스트 간 격리)
    mgmt._notify_scan_locks.clear()
    mgmt._notify_scan_last.clear()

    # sink는 매핑 실패로 skip되도록(외부 의존 없는 결정론) — resolver가 None을 내는 게 기본
    application = FastAPI()
    application.include_router(mgmt.router, prefix="/api/management")
    application.dependency_overrides[get_current_user] = lambda: object()
    return application


@pytest.mark.asyncio
async def test_concurrent_second_request_gets_409(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/management/anomaly/notify-scan"),
            client.post("/api/management/anomaly/notify-scan"),
        )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes == [200, 409]  # 정확히 1건 통과, 1건 잠금 거부


@pytest.mark.asyncio
async def test_failed_scan_does_not_consume_cooldown(app, monkeypatch):
    # 스캔 실패(예외)는 쿨다운을 소진하지 않는다 — 일시 장애 후 즉시 재시도 가능해야 한다
    from core.config import settings

    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 60, raising=False)

    async def boom(_settings, sink, *, scanner=None):
        raise RuntimeError("scan down")

    monkeypatch.setattr("domain.management.scheduler.run_scan", boom)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1 = await client.post("/api/management/anomaly/notify-scan")
        assert r1.status_code == 500  # 실패 자체는 500

        async def ok(_settings, sink, *, scanner=None):
            return 0

        monkeypatch.setattr("domain.management.scheduler.run_scan", ok)
        r2 = await client.post("/api/management/anomaly/notify-scan")
        assert r2.status_code == 200  # 429가 아님 — 실패는 쿨다운 미소진


@pytest.mark.asyncio
async def test_cooldown_returns_429(app, monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "management_scan_manual_cooldown_seconds", 60, raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1 = await client.post("/api/management/anomaly/notify-scan")
        r2 = await client.post("/api/management/anomaly/notify-scan")
    assert r1.status_code == 200
    assert r2.status_code == 429


@pytest.mark.asyncio
async def test_response_contains_delivery_summary(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.post("/api/management/anomaly/notify-scan")
    body = r.json()
    assert set(body) >= {"scanned_findings", "delivered", "skipped", "failed"}


@pytest.mark.asyncio
async def test_different_orgs_do_not_block_each_other(app, monkeypatch):
    # org별 잠금 분리 — 서로 다른 org의 동시 요청은 양쪽 다 통과해야 한다(스펙 §10)
    from itertools import count

    from api.routers import management as mgmt

    seq = count()

    async def rotating_org(user, db):
        return f"org-{next(seq)}"

    monkeypatch.setattr(mgmt, "_require_org_id", rotating_org)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/management/anomaly/notify-scan"),
            client.post("/api/management/anomaly/notify-scan"),
        )
    assert [r1.status_code, r2.status_code] == [200, 200]


@pytest.mark.asyncio
async def test_scanner_is_org_scoped(app, monkeypatch):
    # org 스코프의 핵심 검증 — 스캐너가 org reader를 쓰고 findings tenant가 호출자 org인지
    from types import SimpleNamespace

    from api.routers import management as mgmt

    class FakeReader:
        async def list_campaigns(self):
            return [SimpleNamespace(campaign_id="camp_0", name="테스트")]

        async def get_metrics(self, campaign_id, now):
            return SimpleNamespace(impressions=0)

    captured: dict = {}

    async def capturing_run_scan(_settings, sink, *, scanner=None):
        assert scanner is not None  # 엔드포인트가 org 스캐너를 주입해야 한다
        captured["findings"] = await scanner(_settings)
        return len(captured["findings"])

    monkeypatch.setattr(mgmt, "build_reader", lambda s: FakeReader())
    monkeypatch.setattr("domain.management.scheduler.run_scan", capturing_run_scan)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.post("/api/management/anomaly/notify-scan")
    assert r.status_code == 200
    finding = captured["findings"][0]
    assert finding["tenant_id"] == "org-1"  # "global"이 아니라 호출자 org
    assert finding["meta"]["campaign_id"] == "camp_0"
