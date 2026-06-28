# traffic 링크광고 link_data 구성 검증 — _build_link_creative 순수 함수
from datetime import UTC, datetime, timedelta

import pytest

from domain.management.adapters.meta.writer import _build_link_creative
from domain.management.adapters.mock import MockAdPlatform
from domain.management.contracts.schemas import CampaignConfig


def _cfg(**kw):
    now = datetime.now(UTC)
    return CampaignConfig(
        campaign_id="c",
        tenant_id="t",
        ad_account_id="act_1",
        objective="traffic",
        daily_budget_krw=10000,
        start_at=now,
        end_at=now + timedelta(days=7),
        **kw,
    )


def test_link_creative_maps_copy_and_link():
    cfg = _cfg(headline="제목", body="본문", link_url="https://shop.example.com")
    creative = _build_link_creative(cfg, page_id="page_1", image_hash="hash_1")
    link = creative["object_story_spec"]["link_data"]
    assert link["message"] == "본문"
    assert link["name"] == "제목"
    assert link["link"] == "https://shop.example.com"
    assert link["image_hash"] == "hash_1"
    assert "call_to_action" in link


def test_link_creative_falls_back_to_name_when_copy_missing():
    cfg = _cfg(name="캠페인명", link_url="https://x.example.com")
    creative = _build_link_creative(cfg, page_id="page_1", image_hash=None)
    link = creative["object_story_spec"]["link_data"]
    assert link["message"] == "캠페인명"
    assert "image_hash" not in link


@pytest.mark.asyncio
async def test_full_campaign_traffic_without_link_stops_at_adset():
    writer = MockAdPlatform()
    cfg = _cfg(name="수동", link_url=None)
    result = await writer.create_full_campaign(cfg, "idem-1", page_id="page_1")
    assert result.status.value == "success"  # 광고세트까지 — 현행 동작 유지


@pytest.mark.asyncio
async def test_full_campaign_traffic_with_link_creates_ad():
    writer = MockAdPlatform()
    cfg = _cfg(name="후보", headline="제목", body="본문", link_url="https://x.example.com")
    result = await writer.create_full_campaign(cfg, "idem-2", page_id="page_1")
    assert result.status.value == "success"
