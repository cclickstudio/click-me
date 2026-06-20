"""Task3 create_adset 계약 테스트 — 예산·최적화목표·promoted_object 매핑.

MockTransport로 "요청이 이 형태로 나가는지"만 검증한다(네트워크 0). 같은 production 코드가
live에선 실 Meta로 나가므로, 여기 통과 = 실연동 요청 스키마가 맞다는 뜻.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from domain.management.adapters.meta.client import MetaClient
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.contracts.enums import ExecutionMode, ResultStatus
from domain.management.contracts.schemas import CampaignConfig

NOW = datetime.now(UTC)


def _config(account: str = "111", objective: str = "traffic", name: str | None = None):
    return CampaignConfig(
        campaign_id="camp-local-1",
        tenant_id="org-1",
        ad_account_id=account,
        name=name,
        objective=objective,
        daily_budget_krw=2000,
        start_at=NOW,
        end_at=NOW + timedelta(days=3),
    )


def _capture_writer() -> tuple[MetaAdsWriter, list[tuple[str, bytes]]]:
    captured: list[tuple[str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.url.path, request.content))
        return httpx.Response(200, json={"id": "23843"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    return MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client), captured


def test_create_adset_lead_has_lead_gen_and_promoted_object():
    writer, captured = _capture_writer()
    cfg = _config(objective="leads", name="lead_camp")
    asyncio.run(writer.create_adset(cfg, "120250real", "idem-as1", page_id="PAGE123"))

    path, body = captured[0]
    assert path.endswith("/act_111/adsets")
    assert b"120250real" in body  # 부모 캠페인(Meta id)
    assert b"LEAD_GENERATION" in body  # 리드 최적화 목표
    assert b"PAGE123" in body  # promoted_object의 page_id
    assert b"ON_AD" in body  # 즉석 양식 노출 위치
    assert b"PAUSED" in body  # 안전 — 꺼진 채 생성
    assert b"daily_budget" in body  # 광고세트 레벨 예산


def test_create_adset_traffic_uses_link_clicks_no_promoted_object():
    writer, captured = _capture_writer()
    asyncio.run(writer.create_adset(_config(objective="traffic"), "campX", "idem-as2"))

    _path, body = captured[0]
    assert b"LINK_CLICKS" in body  # 트래픽 최적화
    assert b"promoted_object" not in body  # 트래픽엔 폼 페이지 불필요
    assert b"destination_type" not in body


def test_create_adset_uses_config_targeting():
    # 폼에서 받은 위치·연령·성별이 targeting에 그대로 실린다.
    writer, captured = _capture_writer()
    cfg = _config(objective="traffic").model_copy(
        update={"countries": ("US", "JP"), "age_min": 25, "age_max": 45, "genders": (2,)}
    )
    asyncio.run(writer.create_adset(cfg, "campX", "idem-t"))

    _path, body = captured[0]
    assert b"US" in body and b"JP" in body  # geo_locations.countries
    assert b"age_min" in body and b"25" in body  # 연령
    assert b"genders" in body  # 성별 지정(여성)


def test_create_adset_lead_without_page_id_is_blocked():
    # 리드인데 page_id가 없으면 실 호출 전에 차단(FAILED) — 전송 0.
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=None)
    result = asyncio.run(writer.create_adset(_config(objective="leads"), "campX", "idem-as3"))
    assert result.status is ResultStatus.FAILED
