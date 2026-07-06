# chat sink 테스트 — 판정표 4분기·매핑 skip·race 방어·composite 폴백·요약·실패 격리
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from domain.management.remediation.chat_sink import ChatNotificationSink
from domain.management.remediation.contracts import ConsultResult


def _consult(status="anomaly", campaign_id="camp_1", anomaly="no_delivery"):
    from domain.management.remediation.advisor import build_options

    return ConsultResult(
        status=status,
        campaign_id=campaign_id,
        campaign_name="여름 캠페인",
        anomaly_type=anomaly if status == "anomaly" else "",
        diagnosed_at=datetime.now(UTC).isoformat(),
        message="테스트 메시지 ①②",
        options=build_options(anomaly) if status == "anomaly" else [],
    )


class Store:
    """세션·메시지 영속 포트 fake — last_read_at/기존 consult 시각을 시나리오별로 주입.

    latest_consult_at에 yield 지점(sleep 0)을 둬 race 테스트가 실제 인터리빙을 만들고,
    append가 latest_at을 갱신해 잠금 직렬화 후 두 번째 deliver가 dedup에 걸리게 한다.
    """

    def __init__(self, last_read_at=None, latest_at=None):
        self.last_read_at = last_read_at
        self.latest_at = latest_at
        self.appended: list[tuple[str, str, dict]] = []

    async def find_or_create_session(self, project_id, title):
        return "sess-1", self.last_read_at

    async def latest_consult_at(self, session_id, campaign_id, anomaly_type):
        await asyncio.sleep(0)  # 이벤트 루프 양보 — 잠금 없으면 이중 insert 재현
        return self.latest_at

    async def append_consult(self, session_id, content, meta):
        self.appended.append((session_id, content, meta))
        self.latest_at = datetime.now(UTC)


class FakeFallback:
    def __init__(self):
        self.calls: list[dict] = []

    async def notify(self, tenant_id, title, body, *, meta=None):
        self.calls.append({"tenant_id": tenant_id, "title": title, "meta": meta})


class _Settings:
    openai_api_key = None
    management_consult_cooldown_hours = 24


def _sink(store, *, resolver=None, consult_result="anomaly", fallback=None):
    async def _resolver(campaign_id, *, expected_org_id=None):
        return None if resolver == "none" else ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        if consult_result == "fail":
            return None
        return _consult(status=consult_result)

    return ChatNotificationSink(
        _Settings(),
        fallback=fallback or FakeFallback(),
        store=store,
        resolver=_resolver,
        consult=_consult_fn,
    )


NOW = datetime.now(UTC)


@pytest.mark.asyncio
async def test_delivers_on_new_anomaly():
    store = Store()
    sink = _sink(store)
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    assert len(store.appended) == 1
    _, content, meta = store.appended[0]
    assert meta["kind"] == "remediation_consult"
    assert meta["schema_version"] == 1
    assert meta["org_id"] == "org-9"  # tenant("global")가 아니라 해석된 org가 정본


@pytest.mark.asyncio
async def test_resolver_receives_expected_org_only_for_real_tenant():
    # fail-closed 대조 입력 검증 — "global"은 None, 실 org tenant는 그 org를 넘겨야 한다
    captured: list = []

    async def capturing_resolver(campaign_id, *, expected_org_id=None):
        captured.append(expected_org_id)
        return ("proj-1", "org-9")

    async def _consult_fn(settings, campaign_id, **kw):
        return _consult()

    sink = ChatNotificationSink(
        _Settings(),
        fallback=FakeFallback(),
        store=Store(),
        resolver=capturing_resolver,
        consult=_consult_fn,
    )
    await sink.deliver("global", "제목", "본문", meta={"campaign_id": "camp_1"})
    await sink.deliver("org-7", "제목", "본문", meta={"campaign_id": "camp_2"})
    assert captured == [None, "org-7"]


@pytest.mark.asyncio
async def test_concurrent_delivers_for_same_campaign_insert_once():
    # 스케줄 틱 + 수동 스캔 동시 배달 race — 모듈 잠금으로 정확히 1건만 insert
    store = Store()
    sink = _sink(store)
    o1, o2 = await asyncio.gather(
        sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"}),
        sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"}),
    )
    assert sorted([o1.status, o2.status]) == ["delivered", "skipped"]
    assert len(store.appended) == 1


@pytest.mark.asyncio
async def test_skips_when_no_project_mapping():
    fb = FakeFallback()
    sink = _sink(Store(), resolver="none", fallback=fb)
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "no_project_mapping"
    assert len(fb.calls) == 1  # composite 폴백 — 로그 sink로 위임


@pytest.mark.asyncio
async def test_skips_when_verified_normal():
    sink = _sink(Store(), consult_result="normal")
    out = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "verified_normal"


@pytest.mark.asyncio
async def test_skips_when_bell_pending():
    # 기존 consult 있음 + 세션 미열람(last_read_at이 consult보다 과거/None) → 생략
    store = Store(last_read_at=None, latest_at=NOW - timedelta(hours=1))
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "bell_pending"


@pytest.mark.asyncio
async def test_skips_within_cooldown_after_read():
    latest = NOW - timedelta(hours=2)
    store = Store(last_read_at=NOW - timedelta(hours=1), latest_at=latest)  # 열람함
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "skipped" and out.reason == "cooldown"


@pytest.mark.asyncio
async def test_followup_after_cooldown_with_changed_tone():
    latest = NOW - timedelta(hours=30)  # cooldown 24h 경과
    store = Store(last_read_at=NOW - timedelta(hours=25), latest_at=latest)
    out = await _sink(store).deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out.status == "delivered"
    _, content, _ = store.appended[0]
    assert "아직 계속" in content  # 후속 어조


@pytest.mark.asyncio
async def test_one_failure_does_not_break_loop_and_summary_aggregates():
    class BrokenStore(Store):
        async def append_consult(self, *a):
            raise RuntimeError("db down")

    fb = FakeFallback()
    sink = _sink(BrokenStore(), fallback=fb)
    out1 = await sink.deliver("t1", "제목", "본문", meta={"campaign_id": "camp_1"})
    assert out1.status == "failed"  # 예외가 밖으로 안 나감
    assert len(fb.calls) == 1
    s = sink.summary()
    assert s["failed"][0]["campaign_id"] == "camp_1"
    assert s["delivered"] == 0
