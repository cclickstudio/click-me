# CampaignConfig copy·목적지 필드 검증
from datetime import UTC, datetime, timedelta

from domain.management.contracts.schemas import CampaignConfig


def _base(**kw):
    now = datetime.now(UTC)
    return CampaignConfig(
        campaign_id="camp_1",
        tenant_id="t1",
        ad_account_id="act_1",
        daily_budget_krw=10000,
        start_at=now,
        end_at=now + timedelta(days=7),
        **kw,
    )


def test_copy_and_link_fields_default_none():
    cfg = _base()
    assert cfg.headline is None
    assert cfg.body is None
    assert cfg.link_url is None


def test_copy_and_link_fields_set():
    cfg = _base(headline="제목", body="본문", link_url="https://example.com")
    assert cfg.headline == "제목"
    assert cfg.body == "본문"
    assert cfg.link_url == "https://example.com"
