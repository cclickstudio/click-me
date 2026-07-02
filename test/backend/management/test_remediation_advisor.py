# advisor 테스트 — 재검증(정상/이상)·옵션 풀 고정 스키마·조회 실패 폴백
from __future__ import annotations

from types import SimpleNamespace

import pytest

from domain.management.remediation.advisor import OPTION_POOLS, build_options, consult
from domain.management.remediation.contracts import ConsultResult


class FakeReader:
    """list_campaigns/get_metrics만 흉내 — advisor는 이 두 개만 읽는다."""

    def __init__(self, impressions: int = 1000, fail: bool = False):
        self._impressions = impressions
        self._fail = fail

    async def list_campaigns(self):
        if self._fail:
            raise RuntimeError("meta down")
        return [SimpleNamespace(campaign_id="camp_1", name="여름 캠페인")]

    async def get_metrics(self, campaign_id, now):
        if self._fail:
            raise RuntimeError("meta down")
        return SimpleNamespace(impressions=self._impressions)


class _Settings:
    openai_api_key = None  # LLM polish 비활성 → 결정론 문구


@pytest.mark.asyncio
async def test_consult_verified_normal_when_impressions_positive():
    res = await consult(_Settings(), "camp_1", reader=FakeReader(impressions=500))
    assert isinstance(res, ConsultResult)
    assert res.status == "normal"
    assert res.options == []
    assert "정상" in res.message


@pytest.mark.asyncio
async def test_consult_anomaly_when_no_delivery():
    res = await consult(_Settings(), "camp_1", reader=FakeReader(impressions=0))
    assert res.status == "anomaly"
    assert res.anomaly_type == "no_delivery"
    assert res.campaign_name == "여름 캠페인"
    assert res.diagnosed_at.endswith("+00:00")  # UTC-aware ISO
    assert len(res.options) >= 2
    # 메시지에 번호 옵션이 렌더링돼 있어야 한다
    assert "①" in res.message or "1)" in res.message


@pytest.mark.asyncio
async def test_consult_returns_none_on_reader_failure():
    res = await consult(_Settings(), "camp_1", reader=FakeReader(fail=True))
    assert res is None  # 조회 실패 = 판단 불가(sink는 skip 처리)


@pytest.mark.asyncio
async def test_options_block_survives_llm_polish(monkeypatch):
    # LLM이 인트로를 어떻게 바꿔놔도 옵션 블록은 결정론 렌더러가 항상 붙는다(구조 보증)
    from domain.management.remediation import advisor as adv

    async def rogue_polish(settings, intro):
        return "완전히 다른 텍스트"

    monkeypatch.setattr(adv, "_polish", rogue_polish)
    res = await consult(_Settings(), "camp_1", reader=FakeReader(impressions=0))
    assert "완전히 다른 텍스트" in res.message
    assert "①" in res.message and "번호로 답해 주세요" in res.message


def test_all_option_pools_emit_contract_compliant_options():
    """모든 anomaly_type 풀이 고정 계약 준수 — enum 어휘·index 1부터 연속·tool_hint."""
    for anomaly_type in OPTION_POOLS:
        options = build_options(anomaly_type)
        # ConsultResult validator가 status 규칙·index 연속·tool_hint 등록 여부를 강제
        ConsultResult(
            status="anomaly", campaign_id="c", anomaly_type=anomaly_type, options=options
        )
        assert options[-1].action.value == "OBSERVE"  # 관망은 항상 마지막
