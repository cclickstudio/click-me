# 능동 스케줄러 — 스캔→알림 sink + 기본 off 가드 검증(타이머 미기동)
"""run_scan이 발견분마다 sink로 통지하는지, 기본 스캐너는 빈 결과인지, 스케줄러가 기본 off인지.

실제 타이머(APScheduler)는 띄우지 않는다 — start_scheduler는 비활성이면 즉시 False.
"""

from types import SimpleNamespace

import pytest

from domain.management.notifications import LogNotificationSink, build_notification_sink
from domain.management.scheduler import (
    _agent_scanner,
    _scanner_for,
    account_rule_findings,
    run_scan,
    start_scheduler,
)


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
async def test_run_scan_records_findings_with_injected_recorder():
    """recorder 주입 시 발견분마다 호출되고, recorder 예외는 스캔을 막지 않는다."""

    async def scanner(_s):
        return [
            {"tenant_id": "t1", "title": "게재 점검", "meta": {"campaign_id": "c1"}},
            {"tenant_id": "t1", "title": "소재 피로", "meta": {"campaign_id": "c2"}},
        ]

    recorded = []

    async def recorder(finding):
        if finding["meta"]["campaign_id"] == "c2":
            raise RuntimeError("기록 실패")  # 실패해도 스캔 계속
        recorded.append(finding["meta"]["campaign_id"])

    sink = _FakeSink()
    n = await run_scan(None, sink, scanner=scanner, recorder=recorder)
    assert n == 2  # 통지는 둘 다 나감
    assert recorded == ["c1"]


@pytest.mark.asyncio
async def test_run_scan_default_scanner_runs_and_is_consistent():
    """기본 스캐너(활성 캠페인 게재 점검)가 mock reader로 돌고, 통지 수 == 발견 수."""
    sink = _FakeSink()
    n = await run_scan(SimpleNamespace(), sink)  # use_mock 기본 → mock reader
    assert isinstance(n, int) and n >= 0
    assert len(sink.calls) == n


def test_scheduler_off_by_default_does_not_start():
    assert start_scheduler(SimpleNamespace(management_scheduler_enabled=False)) is False


def test_account_rules_wallet_thresholds():
    """지갑 사용률 95% 이상 = 소진 경보, 80~94% = 주의, 미만 = 무통지 (홈 브리핑과 동일 기준)."""
    alert = account_rule_findings(
        spend_cap_krw=100_000, amount_spent_krw=96_000, projection_krw=0, target_krw=0
    )
    assert [f["meta"]["rule"] for f in alert] == ["wallet_depleted"]
    warn = account_rule_findings(
        spend_cap_krw=100_000, amount_spent_krw=85_000, projection_krw=0, target_krw=0
    )
    assert [f["meta"]["rule"] for f in warn] == ["wallet_warning"]
    quiet = account_rule_findings(
        spend_cap_krw=100_000, amount_spent_krw=50_000, projection_krw=0, target_krw=0
    )
    assert quiet == []


def test_account_rules_budget_pace():
    """런레이트가 월 목표를 넘으면 가드레일 경고 — 비율만 말하고 원값은 노출하지 않는다."""
    over = account_rule_findings(
        spend_cap_krw=0, amount_spent_krw=0, projection_krw=3_500_000, target_krw=3_000_000
    )
    assert [f["meta"]["rule"] for f in over] == ["budget_pace_over"]
    assert over[0]["meta"]["pace_pct"] == 117
    assert "3_500_000" not in over[0]["body"] and "3500000" not in over[0]["body"]
    under = account_rule_findings(
        spend_cap_krw=0, amount_spent_krw=0, projection_krw=2_000_000, target_krw=3_000_000
    )
    assert under == []


def test_account_rules_zero_cap_and_target_are_silent():
    """충전 한도·목표 미설정(0)이면 어떤 룰도 발동하지 않는다(0 나눗셈 방지 포함)."""
    assert (
        account_rule_findings(
            spend_cap_krw=0, amount_spent_krw=90_000, projection_krw=0, target_krw=0
        )
        == []
    )


# ── 에이전트 판단 스캐너 (_agent_scanner) ──────────────────────────


def _fake_metrics(*, impressions=100, frequency=0.0, roas=None):
    from datetime import UTC, datetime

    return SimpleNamespace(
        impressions=impressions,
        frequency=frequency,
        roas=roas,
        as_of=datetime(2026, 7, 4, tzinfo=UTC),
    )


class _FakeReader:
    """스캐너용 캠페인/지표/relevance/계정자금 스텁.

    funding 미지정이면 get_account_funding이 raise → _account_rules_scan은 조용히 []를 낸다.
    """

    def __init__(
        self,
        *,
        impressions=100,
        frequency=0.0,
        roas=None,
        relevance_rank=None,
        spend_cap_krw=None,
        amount_spent_krw=None,
    ):
        from domain.management.contracts.enums import CampaignState

        self._camp = SimpleNamespace(
            campaign_id="c1", name="테스트캠페인", state=CampaignState.ACTIVE
        )
        self._impr = impressions
        self._freq = frequency
        self._roas = roas
        self._rank = relevance_rank
        self._cap = spend_cap_krw
        self._spent = amount_spent_krw

    async def list_campaigns(self):
        return [self._camp]

    async def get_metrics(self, cid, when, date_preset=None):
        if date_preset == "last_7d":
            return _fake_metrics(frequency=self._freq)
        return _fake_metrics(impressions=self._impr, roas=self._roas)

    async def get_relevance_diagnostics(self, cid):
        if self._rank is None:
            return None
        from datetime import UTC, datetime

        from domain.management.contracts.schemas import RelevanceDiagnostics

        return RelevanceDiagnostics(
            campaign_id="c1",
            conversion_rate_ranking=self._rank,
            as_of=datetime(2026, 7, 4, tzinfo=UTC),
        )

    async def get_account_funding(self):
        if self._cap is None:
            raise RuntimeError("no funding")  # → _account_rules_scan은 [] 로 강등
        return SimpleNamespace(spend_cap_krw=self._cap, amount_spent_krw=self._spent or 0)

    async def get_account_spend(self, date_preset="this_month"):
        return 0


@pytest.mark.asyncio
async def test_agent_scanner_flags_zero_impressions(monkeypatch):
    """활성 캠페인 노출 0 → zero_impressions 결정론 센서가 발동(목표 없으니 성과 진단은 생략)."""
    monkeypatch.setattr(
        "domain.management.wiring.build_reader", lambda _s: _FakeReader(impressions=0)
    )
    findings = await _agent_scanner(SimpleNamespace())
    rules = [f["meta"]["rule"] for f in findings]
    assert "zero_impressions" in rules


@pytest.mark.asyncio
async def test_agent_scanner_flags_fatigue(monkeypatch):
    """최근 7일 빈도가 임계 이상 → creative_fatigue 결정론 센서 발동."""
    monkeypatch.setattr(
        "domain.management.wiring.build_reader",
        lambda _s: _FakeReader(impressions=500, frequency=4.0),
    )
    findings = await _agent_scanner(SimpleNamespace())
    rules = [f["meta"]["rule"] for f in findings]
    assert "creative_fatigue" in rules
    assert "zero_impressions" not in rules  # 노출 있음


@pytest.mark.asyncio
async def test_agent_scanner_falls_back_and_never_raises(monkeypatch):
    """reader가 완전히 고장나도 에이전트 스캐너는 raise하지 않고 빈 목록으로 강등."""

    class _BoomReader:
        async def list_campaigns(self):
            raise RuntimeError("meta down")

    monkeypatch.setattr("domain.management.wiring.build_reader", lambda _s: _BoomReader())
    findings = await _agent_scanner(SimpleNamespace())
    assert isinstance(findings, list)  # 폴백(규칙)도 같은 고장 → [] 로 안전 강등


# ── 4룰 커버리지 + 파이프라인 무변경 (T4) ──────────────────────────


@pytest.mark.asyncio
async def test_agent_scanner_covers_all_rule_types(monkeypatch):
    """게재0·소재피로·지갑소진·성과미달을 한 스캔에서 모두 산출(규칙 4종 누락 없음)."""
    from domain.management.contracts.enums import RelevanceRank

    monkeypatch.setattr(
        "domain.management.wiring.build_reader",
        lambda _s: _FakeReader(
            impressions=0,
            frequency=4.0,
            roas=1.0,
            relevance_rank=RelevanceRank.BELOW_AVERAGE_20,
            spend_cap_krw=100_000,
            amount_spent_krw=96_000,
        ),
    )
    findings = await _agent_scanner(SimpleNamespace(management_default_target_roas=3.0))
    rules = {f["meta"]["rule"] for f in findings}
    assert {"zero_impressions", "creative_fatigue", "wallet_depleted"} <= rules
    assert "performance_below_target" in rules  # 에이전트 판단(목표 설정 시)


@pytest.mark.asyncio
async def test_run_scan_with_agent_scanner_notifies_and_records(monkeypatch):
    """모드 agent로 고른 스캐너의 findings가 통지·기록 파이프라인을 그대로 탄다(무변경)."""
    monkeypatch.setattr(
        "domain.management.wiring.build_reader",
        lambda _s: _FakeReader(impressions=0, frequency=4.0),
    )
    recorded: list[str] = []

    async def recorder(f):
        recorded.append(f["meta"]["rule"])

    sink = _FakeSink()
    settings = SimpleNamespace(management_scanner_mode="agent")
    n = await run_scan(settings, sink, scanner=_scanner_for(settings), recorder=recorder)
    assert n == len(sink.calls) == len(recorded)  # 통지 수 == 기록 수 == 발견 수
    assert "zero_impressions" in recorded and "creative_fatigue" in recorded


# ── 스캐너 모드 선택 (_scanner_for) ────────────────────────────────


def test_scanner_for_agent_mode_selects_agent():
    assert _scanner_for(SimpleNamespace(management_scanner_mode="agent")) is _agent_scanner


def test_scanner_for_defaults_to_rule():
    # 기본(미설정) 및 'rule' 모두 None → run_scan이 _default_scanner(규칙)를 쓴다.
    assert _scanner_for(SimpleNamespace()) is None
    assert _scanner_for(SimpleNamespace(management_scanner_mode="rule")) is None


def test_scanner_for_unknown_mode_is_rule():
    # 오타·미지원 값은 안전하게 규칙(None)으로 강등(에이전트 오작동 방지).
    assert _scanner_for(SimpleNamespace(management_scanner_mode="bogus")) is None


def test_settings_scanner_mode_defaults_to_rule():
    """실제 Settings 로드 시 기본값이 rule인지(옵트인 보장)."""
    from core.config import settings

    assert settings.management_scanner_mode == "rule"


@pytest.mark.asyncio
async def test_log_sink_notify_does_not_raise():
    sink = build_notification_sink(SimpleNamespace())
    assert isinstance(sink, LogNotificationSink)
    await sink.notify("t1", "title", "body")  # 예외 없이 통과
