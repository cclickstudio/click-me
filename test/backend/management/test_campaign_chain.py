"""Task4 + 오케스트레이션 — 리드폼·광고 생성 + 캠페인→광고세트→폼→광고 체인 계약.

MockTransport로 요청 스키마와 부모 id 스레딩만 검증(네트워크 0). 전체 체인은 실제 id가
필요해 LIVE 모드 + 경로별 가짜 id를 돌려주는 핸들러로 시뮬레이션한다.
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


def _config(account: str = "111", objective: str = "leads", name: str | None = None):
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
        return httpx.Response(200, json={"id": "obj_1"})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    return MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client), captured


def _routing_writer() -> tuple[MetaAdsWriter, list[tuple[str, bytes]]]:
    """경로별로 다른 id를 돌려주는 LIVE 시뮬 — 체인 id 스레딩 검증용.

    management_create_ad=True를 주입해 전체 캠페인→광고세트→(폼→)광고 체인을 검증한다.
    (기본값 False면 광고세트에서 멈춰 체인 계약 검증이 불완전해짐.)
    """
    import types

    calls: list[tuple[str, bytes]] = []
    table = {
        "/campaigns": "camp_1",
        "/adsets": "adset_1",
        "/leadgen_forms": "form_1",
        "/ads": "ad_1",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append((path, request.content))
        obj_id = next((v for k, v in table.items() if path.endswith(k)), "x")
        return httpx.Response(200, json={"id": obj_id})

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    settings = types.SimpleNamespace(management_create_ad=True)
    return MetaAdsWriter(settings, mode=ExecutionMode.LIVE, client=client), calls


# ── Task4: 리드폼 · 광고 ─────────────────────────────────────────


def test_create_lead_form_posts_to_page_with_privacy_and_email():
    writer, captured = _capture_writer()
    asyncio.run(writer.create_lead_form(_config(name="c"), "idem-f", page_id="PAGE9"))

    path, body = captured[0]
    assert path.endswith("/PAGE9/leadgen_forms")  # 페이지 노드
    assert b"clickme.co.kr" in body  # 개인정보처리방침 URL
    assert b"EMAIL" in body  # 질문


def test_create_ad_creative_references_form_and_page():
    writer, captured = _capture_writer()
    asyncio.run(
        writer.create_ad(_config(name="c"), "ADSET1", "idem-ad", page_id="PAGE9", form_id="FORM1")
    )

    path, body = captured[0]
    assert path.endswith("/act_111/ads")
    assert b"ADSET1" in body  # 부모 광고세트
    assert b"FORM1" in body  # lead_gen_form_id
    assert b"PAGE9" in body  # object_story_spec page_id
    assert b"SIGN_UP" in body  # 폼 여는 CTA
    assert b"PAUSED" in body


# ── 오케스트레이션 체인 ──────────────────────────────────────────


def test_full_campaign_lead_chains_all_four_with_ids():
    writer, calls = _routing_writer()
    result = asyncio.run(
        writer.create_full_campaign(_config(name="leadcamp"), "idem-full", page_id="PAGE9")
    )

    paths = [p for p, _ in calls]
    assert any(p.endswith("/campaigns") for p in paths)
    assert any(p.endswith("/adsets") for p in paths)
    assert any(p.endswith("/leadgen_forms") for p in paths)
    assert any(p.endswith("/ads") for p in paths)
    # 부모 id 스레딩 — 광고세트엔 camp_1, 광고엔 adset_1·form_1이 실린다.
    adset_body = next(b for p, b in calls if p.endswith("/adsets"))
    assert b"camp_1" in adset_body
    ad_body = next(b for p, b in calls if p.endswith("/ads"))
    assert b"adset_1" in ad_body
    assert b"form_1" in ad_body
    assert result.status is ResultStatus.SUCCESS


def test_full_campaign_traffic_stops_at_adset():
    writer, calls = _routing_writer()
    asyncio.run(writer.create_full_campaign(_config(objective="traffic"), "idem-t", page_id="P"))

    paths = [p for p, _ in calls]
    assert any(p.endswith("/adsets") for p in paths)
    assert not any(p.endswith("/leadgen_forms") for p in paths)  # 트래픽은 폼·광고 없음
    assert not any(p.endswith("/ads") for p in paths)


def test_full_campaign_traffic_with_link_creates_link_ad():
    # link_url 있으면 traffic도 링크광고까지 생성 — 실 writer 분기 검증(폼은 없음).
    writer, calls = _routing_writer()
    cfg = _config(objective="traffic").model_copy(
        update={"link_url": "https://shop.example.com", "headline": "제목", "body": "본문"}
    )
    result = asyncio.run(writer.create_full_campaign(cfg, "idem-tl", page_id="P"))

    paths = [p for p, _ in calls]
    assert any(p.endswith("/adsets") for p in paths)
    assert any(p.endswith("/ads") for p in paths)  # link_url → 광고 생성
    assert not any(p.endswith("/leadgen_forms") for p in paths)  # 리드 아님 → 폼 없음
    ad_body = next(b for p, b in calls if p.endswith("/ads"))
    assert b"shop.example.com" in ad_body  # 목적지 link
    assert b"adset_1" in ad_body  # 부모 광고세트 스레딩
    assert result.status is ResultStatus.SUCCESS


def test_activate_sets_status_active():
    # Task5 — 활성화는 status=ACTIVE를 보낸다(과금 시작 트리거). 실 활성화는 사람 몫.
    writer, captured = _capture_writer()
    asyncio.run(writer.activate("OBJ1", "idem-act"))
    _path, body = captured[0]
    assert b"ACTIVE" in body


def test_full_campaign_validate_only_stops_at_campaign():
    # validate_only는 생성 id가 안 와서 체인 불가 → 캠페인 단계까지만(검증).
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.path)
        return httpx.Response(200, json={"success": True})  # id 없음

    client = MetaClient("EAAtest", transport=httpx.MockTransport(handler))
    writer = MetaAdsWriter(mode=ExecutionMode.VALIDATE_ONLY, client=client)
    asyncio.run(writer.create_full_campaign(_config(), "idem-v", page_id="P"))

    assert sum(1 for p in captured if p.endswith("/campaigns")) == 1
    assert not any(p.endswith("/adsets") for p in captured)  # id 없어 체인 중단
