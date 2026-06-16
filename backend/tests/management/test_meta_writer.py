"""🅱 MetaAdsWriter — idem_key 강제·모드 게이팅·DRY_RUN 응답 형태 검증.

LIVE 봉인은 writer가 아니라 executor.DEFAULT_ALLOWED_MODES + use_mock 이중 게이트가
담당한다 (계획 §게이팅). writer 차원 방어는 "자격증명 없으면 미전송".
"""

import pytest

from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import ExecutionMode, ResultStatus


async def test_empty_idem_key_is_rejected():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        await writer.pause("camp-1", "")


async def test_live_mode_without_credentials_does_not_send():
    """LIVE 코드 경로는 존재하나, 자격증명(토큰) 없이는 네트워크로 나가지 않는다.

    실제 LIVE 봉인은 executor 허용 모드 + use_mock 이중 게이트의 몫 (§7 Won't).
    writer 단독 방어 = 토큰 없으면 합성 결과로 폴백.
    """
    writer = MetaAdsWriter(mode=ExecutionMode.LIVE)  # settings 없음 → 클라이언트 미구성
    result = await writer.pause("camp-1", "key-1")
    assert result.status is ResultStatus.SUCCESS
    assert result.platform_response_snapshot["meta_response"] is None
    assert result.platform_response_snapshot["mode"] == "live"


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
