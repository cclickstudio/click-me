# /budget·/anomaly/scan live 로직 — 캠페인별 지표를 배치 1콜로 받는지(N+1 제거) 검증
"""라이브 경로에서 캠페인마다 get_metrics를 순차 호출하지 않고 get_metrics_by_campaign
(level=campaign) 배치로 받는지 잠근다. HTTP·인증을 우회하고 live 구현 함수를 직접 await —
per-campaign get_metrics가 호출되면 FakeReader가 즉시 실패시켜 N+1 회귀를 잡는다.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

from api.routers import management
from domain.management.contracts.enums import CampaignState
from domain.management.contracts.schemas import AccountFunding, MetricsSnapshot


def _snap(cid: str, *, spend: int = 1000, roas: float | None = 2.0, freq: float = 1.0):
    return MetricsSnapshot(
        campaign_id=cid,
        as_of=datetime.now(UTC),
        impressions=1000,
        clicks=50,
        inline_link_clicks=40,
        spend_krw=spend,
        cum_impressions=1000,
        cum_reach=800,
        frequency=freq,
        ctr=0.05,
        cpm_krw=3000,
        cpc_krw=200,
        conversions=5,
        roas=roas,
    )


def _campaigns():
    return [
        SimpleNamespace(
            campaign_id="c1", name="A", state=CampaignState.ACTIVE, daily_budget_krw=10000
        ),
        SimpleNamespace(
            campaign_id="c2", name="B", state=CampaignState.PAUSED, daily_budget_krw=5000
        ),
    ]


class _FakeReader:
    """배치만 응답하고 per-campaign get_metrics 호출은 즉시 실패시키는 감시 리더."""

    def __init__(self, campaigns, *, week_freq=None):
        self._campaigns = campaigns
        self._week_freq = week_freq or {}
        self.batch_presets: list[str] = []
        self.per_campaign_calls = 0

    async def list_campaigns(self, include_archived: bool = False):
        return self._campaigns

    async def get_account_spend(self, date_preset: str = "this_month") -> int:
        return 30000

    async def get_account_daily_spend(self, date_preset: str = "this_month"):
        return [{"date": "2026-07-01", "spend_krw": 30000}]

    async def get_account_funding(self):
        return AccountFunding(
            account_status=1,
            available_balance_krw=5000,
            spend_cap_krw=0,
            amount_spent_krw=30000,
        )

    async def get_metrics_by_campaign(self, ids, since, date_preset: str = "maximum"):
        self.batch_presets.append(date_preset)
        if date_preset == "last_7d":
            return {cid: _snap(cid, freq=self._week_freq.get(cid, 1.0)) for cid in ids}
        return {cid: _snap(cid) for cid in ids}

    async def get_metrics(self, *a, **k):  # N+1 감시 — 호출되면 배치화가 깨진 것
        self.per_campaign_calls += 1
        raise AssertionError("per-campaign get_metrics 호출 — 배치(N+1 제거)가 깨졌습니다")

    async def get_relevance_diagnostics(self, campaign_id: str):
        # 진단은 부가 신호 — 여기선 raise해 LLM 경로를 타지 않게(diagnose_campaign이 None 반환)
        raise RuntimeError("relevance 미지원(테스트)")


async def test_budget_live_uses_batch_not_n_plus_1():
    reader = _FakeReader(_campaigns())
    # _budget_status_live는 live 구현 자체 — use_mock 분기·인증과 무관하게 직접 검증.
    body = await management._budget_status_live(reader, str(uuid.uuid4()))

    assert reader.per_campaign_calls == 0  # 순차 get_metrics 없음
    assert "this_month" in reader.batch_presets  # 캠페인별 지표는 배치로
    names = {c["name"]: c for c in body["campaigns"]}
    assert names["A"]["spend_krw"] == 1000
    assert names["A"]["roas"] == 2.0
    assert len(body["campaigns"]) == 2


async def test_anomaly_scan_live_batches_metrics_and_fatigue():
    # c1(active)의 최근 7일 빈도를 임계 이상으로 → AUDIENCE_FATIGUE 이상 감지
    reader = _FakeReader(_campaigns(), week_freq={"c1": 3.5})
    # anomaly_scan은 use_mock=True면 빈 결과로 조기 반환 → live만 로직이 돈다. 원본 settings를
    # mutate하지 않도록 use_mock만 바꾼 복사본으로 모듈 속성을 with-스코프 patch(누수 0).
    live = management.settings.model_copy(update={"use_mock": False})
    with mock.patch.object(management, "settings", live):
        body = await management.anomaly_scan(reader=reader, target_roas=None)

    assert reader.per_campaign_calls == 0  # 순차 get_metrics 없음
    assert "last_7d" in reader.batch_presets  # 진행 중 7일 빈도도 배치로
    assert body["scanned"] == 2
    fatigue = [
        a for a in body["anomalies"] if a["diagnosis"].get("anomaly_type") == "AUDIENCE_FATIGUE"
    ]
    assert len(fatigue) == 1
    assert fatigue[0]["campaign_id"] == "c1"
