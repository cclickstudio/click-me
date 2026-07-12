# mock 데모 캠페인 스토어 — 정본 단일화(초기값)·상태화(set_budget 반영·writer 갱신) 검증
from datetime import UTC, datetime

import pytest

from domain.management.adapters import demo_store
from domain.management.adapters.demo_store import DemoBudgetWriter
from domain.management.adapters.mock import MockAdPlatform
from domain.management.contracts.enums import ExecutionMode, ResultStatus
from domain.management.contracts.schemas import ActionResult


@pytest.fixture(autouse=True)
def _reset_store():
    """스토어는 싱글턴(모듈 상태) — 테스트 간 예산 오염 방지."""
    demo_store.reset()
    yield
    demo_store.reset()


def test_initial_values_match_legacy_campaigns_demo():
    """① 초기값 = 기존 _CAMPAIGNS_DEMO 5캠(이름·상태·예산·고장) 그대로."""
    camps = demo_store.campaigns()
    assert [c[0] for c in camps] == ["camp_1", "camp_2", "camp_3", "camp_4", "camp_5"]
    assert [c[3] for c in camps] == [40_000, 25_000, 15_000, 10_000, 10_000]
    assert camps[0][1] == "여름 신상 원피스"
    assert demo_store.get_budget("camp_1") == 40_000
    assert demo_store.get_budget("unknown") == 0


async def test_set_budget_reflected_in_mock_reader_and_router():
    """② set_budget 후 mock reader 목록과 라우터 _current_daily_budget이 같은 값을 본다."""
    demo_store.set_budget("camp_1", 52_000)

    infos = await MockAdPlatform().list_campaigns()
    by_id = {c.campaign_id: c.daily_budget_krw for c in infos}
    assert by_id["camp_1"] == 52_000

    from api.routers.management import _current_daily_budget

    assert await _current_daily_budget(MockAdPlatform(), "camp_1") == 52_000
    # campaigns() 정본도 같은 값 — 목록·상세·예산 페이지가 한 소스를 본다.
    assert next(c[3] for c in demo_store.campaigns() if c[0] == "camp_1") == 52_000


class _FailingWriter:
    """inner 실패 시 스토어가 갱신되지 않아야 함을 검증하기 위한 가짜 writer."""

    async def adjust_budget(self, campaign_id: str, amount_krw: int, idem_key: str) -> ActionResult:
        return ActionResult(
            result_id="r1",
            approval_id="",
            status=ResultStatus.FAILED,
            executed_at=datetime.now(UTC),
            idempotency_key=idem_key,
        )


async def test_writer_updates_store_only_on_success():
    """③ DemoBudgetWriter — inner 성공(DRY_RUN=SUCCESS) 시 스토어 갱신, 실패 시 미갱신."""
    from domain.management.adapters.meta.writer import MetaAdsWriter

    writer = DemoBudgetWriter(MetaAdsWriter(None, mode=ExecutionMode.DRY_RUN))
    result = await writer.adjust_budget("camp_2", 33_000, "idem-1")
    assert result.status is ResultStatus.SUCCESS
    assert demo_store.get_budget("camp_2") == 33_000

    failing = DemoBudgetWriter(_FailingWriter())
    result = await failing.adjust_budget("camp_3", 99_000, "idem-2")
    assert result.status is ResultStatus.FAILED
    assert demo_store.get_budget("camp_3") == 15_000
