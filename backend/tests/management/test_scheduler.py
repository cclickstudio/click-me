# 능동 스케줄러 — 스캔→알림 sink + 기본 off 가드 검증(타이머 미기동)
"""run_scan이 발견분마다 sink로 통지하는지, 기본 스캐너는 빈 결과인지, 스케줄러가 기본 off인지.

실제 타이머(APScheduler)는 띄우지 않는다 — start_scheduler는 비활성이면 즉시 False.
"""

from types import SimpleNamespace

import pytest

from domain.management.notifications import LogNotificationSink, build_notification_sink
from domain.management.scheduler import run_scan, start_scheduler


class _FakeSink:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.calls.append((tenant_id, title))


@pytest.mark.asyncio
async def test_run_scan_notifies_each_finding():
    async def scanner(_s):
        return [
            {"tenant_id": "t1", "title": "BID_LOSS", "body": "cpm 급등"},
            {"tenant_id": "t2", "title": "REVIEW_REJECTED", "body": "거절"},
        ]

    sink = _FakeSink()
    n = await run_scan(None, sink, scanner=scanner)
    assert n == 2
    assert ("t1", "BID_LOSS") in sink.calls
    assert ("t2", "REVIEW_REJECTED") in sink.calls


@pytest.mark.asyncio
async def test_run_scan_default_scanner_is_empty():
    sink = _FakeSink()
    assert await run_scan(SimpleNamespace(), sink) == 0
    assert sink.calls == []


def test_scheduler_off_by_default_does_not_start():
    assert start_scheduler(SimpleNamespace(management_scheduler_enabled=False)) is False


@pytest.mark.asyncio
async def test_log_sink_notify_does_not_raise():
    sink = build_notification_sink(SimpleNamespace())
    assert isinstance(sink, LogNotificationSink)
    await sink.notify("t1", "title", "body")  # 예외 없이 통과
