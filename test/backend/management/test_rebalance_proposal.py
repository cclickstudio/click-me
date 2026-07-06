# 예산 리밸런싱 제안(하이브리드) — 1개 단일 조정 / 2개+ 이전 로직 테스트
"""insights.rebalance_proposal의 캠페인 수별 분기를 실측 없이(fake reader) 검증한다.

- 1개: 소진율(7일 예산 활용도) 기준 증액/감액/적정(제안 없음).
- 2개+: 저효율→고효율 이전(kind=transfer), CPC 격차 게이트.
"""

from types import SimpleNamespace

import pytest

from domain.management.contracts.enums import CampaignState
from domain.management.insights import rebalance_proposal


def _camp(cid, name, budget, *, state=CampaignState.ACTIVE, budget_type="daily"):
    return SimpleNamespace(
        campaign_id=cid,
        name=name,
        daily_budget_krw=budget,
        lifetime_budget_krw=0,
        budget_type=budget_type,
        state=state,
        ended_at=None,
    )


def _metrics(*, clicks, spend, cpc):
    return SimpleNamespace(clicks=clicks, spend_krw=spend, cpc_krw=cpc)


class _FakeReader:
    def __init__(self, campaigns, metrics):
        self._campaigns = campaigns
        self._metrics = metrics

    async def list_campaigns(self):
        return self._campaigns

    async def get_metrics(self, cid, _now, date_preset=None):  # noqa: ARG002
        return self._metrics[cid]


@pytest.fixture(autouse=True)
def _fixed_floor(monkeypatch):
    """정책 조회를 최소예산 1,000원으로 고정 — floor 계산 결정론화."""

    async def fake_policy(_reader):
        return {"min_daily_budget_krw": 1_000}

    monkeypatch.setattr("domain.management.insights.get_campaign_policy", fake_policy)


@pytest.mark.asyncio
async def test_single_campaign_high_util_proposes_increase():
    """1개 · 소진율 90%+ → 증액(kind=adjust·direction=increase)."""
    reader = _FakeReader(
        [_camp("c1", "여름 캠페인", 10_000)],
        {"c1": _metrics(clicks=100, spend=66_000, cpc=660)},  # util=0.943
    )
    out = await rebalance_proposal(reader)
    prop = out["proposal"]
    assert prop["kind"] == "adjust"
    assert prop["direction"] == "increase"
    assert prop["campaign"]["campaign_id"] == "c1"
    assert prop["move_krw"] == 2_000
    assert prop["campaign"]["after_krw"] == 12_000


@pytest.mark.asyncio
async def test_single_campaign_low_util_proposes_decrease():
    """1개 · 소진율 50% 이하 → 감액. 최소예산(1,000) 아래로는 안 내려간다."""
    reader = _FakeReader(
        [_camp("c1", "잠재 캠페인", 10_000)],
        {"c1": _metrics(clicks=30, spend=21_000, cpc=700)},  # util=0.3
    )
    out = await rebalance_proposal(reader)
    prop = out["proposal"]
    assert prop["kind"] == "adjust"
    assert prop["direction"] == "decrease"
    assert prop["move_krw"] == 2_000
    assert prop["campaign"]["after_krw"] == 8_000


@pytest.mark.asyncio
async def test_single_campaign_mid_util_no_proposal():
    """1개 · 소진율 적정 범위(50~90%) → 제안 없음."""
    reader = _FakeReader(
        [_camp("c1", "적정 캠페인", 10_000)],
        {"c1": _metrics(clicks=50, spend=49_000, cpc=980)},  # util=0.7
    )
    out = await rebalance_proposal(reader)
    assert out["proposal"] is None
    assert "적정" in out["note"]


@pytest.mark.asyncio
async def test_two_campaigns_transfer_low_to_high_efficiency():
    """2개+ · CPC 격차 1.2배 초과 → 저효율(높은 CPC)→고효율(낮은 CPC) 이전."""
    reader = _FakeReader(
        [_camp("c_best", "고효율", 10_000), _camp("c_worst", "저효율", 10_000)],
        {
            "c_best": _metrics(clicks=100, spend=20_000, cpc=200),
            "c_worst": _metrics(clicks=20, spend=10_000, cpc=500),  # 2.5배
        },
    )
    out = await rebalance_proposal(reader)
    prop = out["proposal"]
    assert prop["kind"] == "transfer"
    assert prop["from"]["campaign_id"] == "c_worst"
    assert prop["to"]["campaign_id"] == "c_best"
    assert prop["move_krw"] == 2_000
    assert prop["from"]["after_krw"] == 8_000
    assert prop["to"]["after_krw"] == 12_000


@pytest.mark.asyncio
async def test_no_eligible_campaign_returns_note():
    """진행 중(일예산형) 캠페인이 없으면 제안 없음(안내만)."""
    reader = _FakeReader(
        [_camp("c1", "종료 캠페인", 10_000, state=CampaignState.ENDED)],
        {},
    )
    out = await rebalance_proposal(reader)
    assert out["proposal"] is None
    assert out["note"]
