"""Meta 어댑터 계약 테스트 — 녹화 Graph API 응답으로 매핑·게이팅 검증 (네트워크 0).

httpx.MockTransport로 "URL → 녹화 JSON"을 재현한다 (generator/adapters/instagram.py 패턴).
실제 Meta 호출은 일어나지 않는다.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from domain.management.adapters.meta.client import MetaApiError, MetaClient, mask_token
from domain.management.adapters.meta.reader import MetaAdsReader, _count_conversions, _is_past
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import CampaignState, ExecutionMode
from domain.management.contracts.schemas import CampaignConfig

_FIXTURES = Path(__file__).parents[1].parent / "domain/management/evals/fixtures/meta"


def _load(name: str) -> dict:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


def _reader_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    # /campaigns 분기는 status 체크보다 먼저 — 목록 요청 필드에도 effective_status 포함
    if path.endswith("/campaigns"):
        return httpx.Response(200, json=_load("campaigns_v21.json"))
    if path.endswith("/adsets"):
        return httpx.Response(200, json=_load("adsets_v21.json"))
    if path.endswith("/ads"):
        return httpx.Response(200, json=_load("ads_creative_v21.json"))
    if "/insights" in path:
        breakdowns = request.url.params.get("breakdowns")
        if breakdowns == "publisher_platform":
            return httpx.Response(200, json=_load("insights_platform_v21.json"))
        if breakdowns == "age,gender":
            return httpx.Response(200, json=_load("insights_demographic_v21.json"))
        return httpx.Response(200, json=_load("insights_v21.json"))
    if "funding_source_details" in (request.url.params.get("fields") or ""):
        return httpx.Response(200, json=_load("account_funding_v21.json"))
    if "/delivery_estimate" in path:
        return httpx.Response(200, json=_load("delivery_estimate_v21.json"))
    if "effective_status" in (request.url.params.get("fields") or ""):
        return httpx.Response(200, json=_load("campaign_status_active_v21.json"))
    return httpx.Response(200, json={"error": {"message": "unexpected", "code": 1}})


def _reader(token: str = "EAAtest_secret_token") -> MetaAdsReader:
    client = MetaClient(token, api_version="v21.0", transport=httpx.MockTransport(_reader_handler))
    return MetaAdsReader(client=client)


def _reader_with_account(account: str = "111222333") -> MetaAdsReader:
    client = MetaClient(
        "EAAtest_secret_token",
        ad_account_id=account,
        api_version="v21.0",
        transport=httpx.MockTransport(_reader_handler),
    )
    return MetaAdsReader(client=client)


def _config() -> CampaignConfig:
    now = datetime.now(UTC)
    return CampaignConfig(
        campaign_id="23842000000000123",
        tenant_id="org_1",
        ad_account_id="111222333",
        daily_budget_krw=100_000,
        start_at=now,
        end_at=now,
    )


# ── reader 매핑 ──────────────────────────────────────────────────


def test_get_metrics_maps_insights_json():
    snap = asyncio.run(_reader().get_metrics("23842000000000123", datetime.now(UTC)))
    assert snap.impressions == 12000
    assert snap.clicks == 204
    assert snap.spend_krw == 95000
    assert snap.ctr == pytest.approx(0.017)  # Meta 백분율(1.7) → 비율 환산
    assert snap.cum_reach == 8000
    assert snap.conversions == 9
    assert snap.purchase_value_krw == 475_000
    assert snap.cvr == pytest.approx(0.05)
    assert snap.roas == pytest.approx(5.0)
    assert snap.as_of == datetime(2026, 6, 15, tzinfo=UTC)


def test_count_conversions_autodetects_lead_when_no_purchase():
    # 구매를 안 파는 캠페인 — 리드가 잡히면 그걸 전환으로 센다.
    actions = [{"action_type": "onsite_conversion.lead_grouped", "value": "7"}]
    assert _count_conversions(actions) == (7.0, "lead")


def test_count_conversions_prefers_purchase_over_other_events():
    actions = [
        {"action_type": "lead", "value": "20"},
        {"action_type": "omni_purchase", "value": "3"},
    ]
    assert _count_conversions(actions) == (3.0, "purchase")


def test_count_conversions_measured_zero_vs_untracked():
    assert _count_conversions([]) == (0.0, None)  # 추적은 켜졌는데 전환 0(측정된 0)
    assert _count_conversions(None) == (None, None)  # 전환 추적 미설정


def test_get_estimate_maps_delivery_estimate_json():
    est = asyncio.run(_reader().get_estimate(_config()))
    assert est.estimate_ready is True
    assert est.estimate_mau_lower == 1_500_000
    assert est.estimate_mau_upper == 2_000_000
    assert len(est.daily_outcomes_curve) == 2


def test_get_state_maps_effective_status():
    state = asyncio.run(_reader().get_state("23842000000000123"))
    assert state is CampaignState.ACTIVE


def test_get_platform_breakdown_splits_fb_ig():
    rows = asyncio.run(_reader().get_platform_breakdown("23842000000000123", datetime.now(UTC)))
    by = {r.platform: r for r in rows}
    assert by["facebook"].impressions == 25
    assert by["instagram"].impressions == 799
    assert by["instagram"].spend_krw == 4895
    assert by["facebook"].clicks == 2


def test_get_demographic_breakdown_maps_age_gender():
    rows = asyncio.run(_reader().get_demographic_breakdown("23842000000000123", datetime.now(UTC)))
    by = {(r.age, r.gender): r for r in rows}
    assert by[("25-34", "female")].impressions == 420
    assert by[("25-34", "female")].spend_krw == 2600
    assert by[("25-34", "male")].clicks == 18
    assert by[("35-44", "female")].reach == 178


def test_get_creatives_maps_ad_image_and_copy():
    rows = asyncio.run(_reader().get_creatives("23842000000000123"))
    assert len(rows) == 2
    assert rows[0].ad_id == "23842000000000777"
    assert rows[0].ad_name == "여름 세일 · 메인 비주얼"
    # 동적 광고(asset_feed_spec) 우선 — image_url보다 고해상 자산 URL을 고른다
    assert rows[0].image_url == "https://scontent.example.com/ad_asset_hi_a.jpg"
    assert rows[0].thumbnail_url == "https://scontent.example.com/ad_thumb_a.jpg"
    assert rows[0].headline == "여름 세일 최대 50%"
    assert rows[0].primary_text == "시즌 오프 특가, 지금 만나보세요."
    # asset_feed_spec 없는 광고는 image_url 폴백
    assert rows[1].image_url == "https://scontent.example.com/ad_image_b.jpg"
    assert rows[1].ad_name == "여름 세일 · 모델 컷"


def test_get_account_funding_detects_prepaid_exhausted():
    f = asyncio.run(_reader_with_account().get_account_funding())
    assert f.delivery_blocked is True
    assert f.block_reason == "선불 잔액 부족"
    assert f.available_balance_krw == 0


def test_list_campaigns_maps_campaign_json():
    campaigns = asyncio.run(_reader_with_account().list_campaigns())
    assert len(campaigns) == 2
    first = campaigns[0]
    assert first.campaign_id == "120250000000000001"
    assert first.name == "여름 세일"
    assert first.state is CampaignState.ACTIVE
    assert first.daily_budget_krw == 50000  # 캠페인(CBO) 예산 — KRW offset=1
    assert campaigns[1].state is CampaignState.PAUSED
    # 캠페인 노드에 예산 없음 → 광고세트 일예산 합(15000+15000)으로 보완
    assert campaigns[1].daily_budget_krw == 30000


def test_is_past_detects_expired_schedule():
    assert _is_past("2000-01-01T00:00:00+0900") is True  # 과거
    assert _is_past("2999-12-31T00:00:00+0900") is False  # 미래
    assert _is_past(None) is False  # 무기한(종료일 없음)
    assert _is_past("") is False
    assert _is_past("garbage") is False  # 파싱 실패 → 종료 아님(보수적)


def test_list_campaigns_marks_past_stop_time_as_ended():
    # effective_status가 ACTIVE라도 stop_time이 과거면 종료로 본다(충전해도 재개 안 됨).
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/campaigns"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "120250000000000099",
                            "name": "기간 끝난 트래픽",
                            "effective_status": "ACTIVE",
                            "daily_budget": "10000",
                            "stop_time": "2000-01-01T00:00:00+0900",
                        }
                    ]
                },
            )
        if request.url.path.endswith("/adsets"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(200, json={"data": []})

    client = MetaClient(
        "EAAtest",
        ad_account_id="111",
        api_version="v21.0",
        transport=httpx.MockTransport(handler),
    )
    campaigns = asyncio.run(MetaAdsReader(client=client).list_campaigns())
    assert campaigns[0].state is CampaignState.ENDED


# ── client 에러·마스킹 ───────────────────────────────────────────


def test_client_raises_meta_api_error_without_token_leak():
    token = "EAAtop_secret_value"

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("error_oauth_v21.json"))

    client = MetaClient(token, transport=httpx.MockTransport(handler))
    with pytest.raises(MetaApiError) as exc:
        asyncio.run(client.get("me"))
    assert exc.value.code == 190
    assert exc.value.is_auth_error is True  # 토큰 만료 → '재연결 필요' 안내로 매핑
    assert token not in str(exc.value)  # 토큰 평문 미노출 (게이트 #8)


def test_meta_api_error_auth_vs_other():
    assert MetaApiError(190, None, "expired").is_auth_error is True
    assert MetaApiError(102, None, "session").is_auth_error is True
    assert MetaApiError(4, None, "rate").is_auth_error is False  # 레이트리밋은 인증 오류 아님
    assert MetaApiError(100, None, "param").is_auth_error is False


def test_mask_token_hides_secret():
    assert mask_token("EAAabcdef.very.secret") == "EAAa…(masked)"
    assert mask_token(None) == "<none>"
    assert mask_token("") == "<none>"


def test_client_repr_masks_token():
    assert "secret" not in repr(MetaClient("EAAsecretvalue", ad_account_id="111"))


# ── writer 모드 게이팅 ───────────────────────────────────────────


def _capturing_writer(mode: ExecutionMode, sent: list[bytes]) -> MetaAdsWriter:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request.content)
        return httpx.Response(200, json={"id": "23842000000000123", "success": True})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    return MetaAdsWriter(mode=mode, client=client)


def test_dry_run_does_not_send():
    sent: list[bytes] = []
    writer = _capturing_writer(ExecutionMode.DRY_RUN, sent)
    result = asyncio.run(writer.pause("23842000000000123", "idem-1"))
    assert sent == []  # 전송 0건
    assert result.platform_response_snapshot["dry_run"] is True
    assert result.platform_response_snapshot["meta_response"] is None


def test_validate_only_sends_with_validate_only():
    sent: list[bytes] = []
    writer = _capturing_writer(ExecutionMode.VALIDATE_ONLY, sent)
    result = asyncio.run(writer.adjust_budget("23842000000000123", 120_000, "idem-2"))
    assert len(sent) == 1
    assert b"validate_only" in sent[0]  # execution_options 부착
    assert b"daily_budget" in sent[0]
    assert result.platform_response_snapshot["dry_run"] is True  # validate_only = 변경 없음


def test_live_sends_without_validate_only():
    sent: list[bytes] = []
    writer = _capturing_writer(ExecutionMode.LIVE, sent)
    result = asyncio.run(writer.pause("23842000000000123", "idem-3"))
    assert len(sent) == 1
    assert b"validate_only" not in sent[0]
    assert result.platform_response_snapshot["dry_run"] is False


def test_writer_requires_idem_key():
    writer = MetaAdsWriter(mode=ExecutionMode.DRY_RUN)
    with pytest.raises(ValueError, match="idem_key"):
        asyncio.run(writer.pause("23842000000000123", ""))
