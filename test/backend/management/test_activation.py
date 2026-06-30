# 게재 시작(활성화) 트리·지출 상한·크레딧 정산 단위 테스트
"""writer.activate_tree / set_spend_cap 와 billing.spent_for 정산 로직 검증.

httpx.MockTransport로 "GET 자식 id → POST ACTIVE" 흐름을 재현한다(test_meta_adapter 패턴).
"""

import asyncio

import httpx

from domain.billing.service.billing_service import BillingService
from domain.billing.toss_client import TossPaymentsClient
from domain.management.adapters.meta.client import MetaClient
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import ExecutionMode, ResultStatus


def _tree_writer(sent: list[dict]) -> MetaAdsWriter:
    """LIVE writer — GET adsets/ads는 자식 2개씩, POST는 성공. POST 본문을 sent에 기록."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET":
            if path.endswith("/adsets"):
                return httpx.Response(200, json={"data": [{"id": "as1"}, {"id": "as2"}]})
            if path.endswith("/ads"):
                return httpx.Response(200, json={"data": [{"id": "ad1"}, {"id": "ad2"}]})
            return httpx.Response(200, json={"data": []})
        # POST — 본문 파싱해 어떤 객체에 무엇을 보냈는지 기록
        body = dict(p.split("=", 1) for p in request.content.decode().split("&") if "=" in p)
        sent.append({"path": path, **body})
        return httpx.Response(200, json={"id": path.rsplit("/", 1)[-1], "success": True})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    return MetaAdsWriter(mode=ExecutionMode.LIVE, client=client)


def test_activate_tree_activates_campaign_adsets_and_ads():
    sent: list[dict] = []
    writer = _tree_writer(sent)
    result = asyncio.run(writer.activate_tree("camp123", "idem-act"))
    assert result.status is ResultStatus.SUCCESS
    # 캠페인 + 광고세트 2 + 광고 2 = 5건 모두 ACTIVE 전송
    active_targets = [s["path"].rsplit("/", 1)[-1] for s in sent if s.get("status") == "ACTIVE"]
    assert active_targets == ["camp123", "as1", "as2", "ad1", "ad2"]
    # 결과 스냅샷에 캠페인 id 태깅
    assert result.platform_response_snapshot["campaign_meta_id"] == "camp123"


def test_activate_tree_dry_run_campaign_only():
    # 비전송 모드는 자식을 조회하지 않고 캠페인 단계까지만(합성).
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    result = asyncio.run(writer.activate_tree("camp123", "idem-dry"))
    assert result.status is ResultStatus.SUCCESS
    assert result.platform_response_snapshot["dry_run"] is True


def test_set_spend_cap_live_sends_amount():
    sent: list[dict] = []
    writer = _tree_writer(sent)
    result = asyncio.run(writer.set_spend_cap("camp123", 45630, "idem-cap"))
    assert result.status is ResultStatus.SUCCESS
    cap_posts = [s for s in sent if "spend_cap" in s]
    assert len(cap_posts) == 1
    assert cap_posts[0]["spend_cap"] == "45630"
    assert cap_posts[0]["path"].endswith("camp123")


class _FakeToss(TossPaymentsClient):
    """confirm을 네트워크 없이 성공 처리하는 테스트 더블."""

    def __init__(self) -> None:  # noqa: D401 — 시크릿 불요
        pass

    async def confirm(self, payment_key: str, order_id: str, amount_krw: int) -> dict:
        return {"status": "DONE", "orderId": order_id, "totalAmount": amount_krw}


async def test_spent_for_sums_only_matching_ref():
    svc = BillingService(_FakeToss())
    org = "org-x"
    # 충전 30,000 (원장 CHARGE를 confirm 경유로)
    order = await svc.create_order(org, 30_000)
    await svc.confirm("pk_1", order.order_id, 30_000)
    assert await svc.balance(org) == 30_000
    # 캠페인 A에 2회 증분 차감
    await svc.record_spend(org, 4_000, ref_id="campA")
    await svc.record_spend(org, 6_000, ref_id="campA")
    await svc.record_spend(org, 1_000, ref_id="campB")
    assert await svc.spent_for(org, "campA") == 10_000
    assert await svc.spent_for(org, "campB") == 1_000
    assert await svc.balance(org) == 30_000 - 11_000
