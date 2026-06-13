"""🅱 MetaAdsWriter stub — idem_key 강제·LIVE 차단·DRY_RUN 응답 형태 검증."""

import pytest

from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import ExecutionMode, ResultStatus


async def test_empty_idem_key_is_rejected():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        await writer.pause("camp-1", "")


async def test_live_mode_writes_are_not_implemented():
    """LIVE 쓰기는 7/8 스코프 제외 (Won't, §7) — 물리적으로 막혀 있어야 한다."""
    writer = MetaAdsWriter(mode=ExecutionMode.LIVE)
    with pytest.raises(NotImplementedError):
        await writer.pause("camp-1", "key-1")
    with pytest.raises(NotImplementedError):
        await writer.adjust_budget("camp-1", 10_000, "key-1")


async def test_negative_krw_is_rejected():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="KRW"):
        await writer.adjust_budget("camp-1", -1, "key-1")


async def test_dry_run_snapshot_shape():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.adjust_budget("camp-1", 40_000, "key-1")

    assert result.status is ResultStatus.SUCCESS
    assert result.idempotency_key == "key-1"
    snapshot = result.platform_response_snapshot
    assert snapshot["dry_run"] is True
    assert snapshot["operation"] == "adjust_budget"
    assert snapshot["amount_krw"] == 40_000


async def test_mode_read_from_settings_object():
    class FakeSettings:
        management_execution_mode = "sandbox_contract"

    writer = MetaAdsWriter(FakeSettings())
    result = await writer.pause("camp-1", "key-1")
    assert result.platform_response_snapshot["mode"] == "sandbox_contract"


async def test_preview_needs_no_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    url = await writer.preview("camp-1")
    assert "camp-1" in url


async def test_replace_creative_carries_creative_id():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = await writer.replace_creative("camp-1", "cand-42", "key-1")

    assert result.status is ResultStatus.SUCCESS
    snapshot = result.platform_response_snapshot
    assert snapshot["operation"] == "replace_creative"
    assert snapshot["creative_id"] == "cand-42"


async def test_replace_creative_requires_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        await writer.replace_creative("camp-1", "cand-42", "")
