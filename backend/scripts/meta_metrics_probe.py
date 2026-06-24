"""실 Meta 캠페인 지표 검증 — reader로 실데이터를 끌어 감지 파이프라인까지 돌린다.

settings(.env)의 광고계정에서 캠페인을 자동 탐색해 각 캠페인의 상태(get_state)·누적
지표(get_metrics)를 출력하고, 한 캠페인은 하루치 시간별 지표(fetch_hourly_metrics)로
감지(기대곡선 비교→이상구간→결정론 진단)를 실행한다. use_mock과 무관하게 항상 실
MetaAdsReader를 쓴다(실데이터 검증이 목적 — mock 분기 우회).

실행:  cd backend && uv run python scripts/meta_metrics_probe.py [--since-days 7] [--campaign <id>]
.env:  META_ACCESS_TOKEN · META_AD_ACCOUNT_ID
주의:  계정에 캠페인이 없거나 지출 0이면 빈 값이 정상 — 게재·지출 후 다시 실행.
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import argparse
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from core.config import settings
from domain.management.adapters.meta.client import (
    MetaApiError,
    build_meta_client,
    normalize_ad_account,
)
from domain.management.adapters.meta.reader import MetaAdsReader
from domain.management.contracts.policy import DAILY_BUDGET_KRW
from domain.management.detection.deterministic_dx import diagnose
from domain.management.detection.exposure_model import (
    expected_hourly_impressions,
    find_anomaly_window,
)

_TENANT = "probe-tenant"  # 진단 입력용 placeholder (실 테넌트 무관)


def _fmt_metrics(snap) -> str:
    return (
        f"노출 {snap.impressions} · 클릭 {snap.clicks} · 지출 ₩{snap.spend_krw} · "
        f"도달 {snap.cum_reach} · CTR {snap.ctr:.4f} · CPM ₩{snap.cpm_krw} · CPC ₩{snap.cpc_krw}"
    )


async def _list_campaigns(client, acct: str) -> list[dict]:
    payload = await client.get(
        f"{acct}/campaigns",
        {"fields": "id,name,status,effective_status,daily_budget", "limit": 25},
    )
    return payload.get("data", [])


async def _run_detection(reader: MetaAdsReader, campaign_id: str, daily_budget_krw: int) -> None:
    day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    snapshots = await reader.fetch_hourly_metrics(campaign_id, day)
    if not snapshots:
        print("  · 오늘 시간별 데이터 없음 (게재 전 / 지출 0) — 감지 스킵", flush=True)
        return
    observed = [s.impressions for s in snapshots]
    expected = expected_hourly_impressions(daily_budget_krw)
    window = find_anomaly_window(expected, observed)
    print(f"  · 시간별 {len(snapshots)}행 수신, 이상구간={window or '없음'}", flush=True)
    if not window:
        print("  · 이상 없음 — 정상 게재 판정", flush=True)
        return
    dx = diagnose(_TENANT, campaign_id, snapshots, expected, window)
    print(f"  · 진단: {dx.anomaly_type} (status={dx.status}, conf={dx.confidence})", flush=True)


async def run(since_days: int, only_campaign: str | None) -> None:
    acct = normalize_ad_account(settings.meta_ad_account_id)
    client = build_meta_client(settings)
    reader = MetaAdsReader(settings)
    since = datetime.now(UTC) - timedelta(days=since_days)
    print(f"계정 {acct} · 최근 {since_days}일 · API {settings.meta_graph_api_version}", flush=True)

    try:
        campaigns = await _list_campaigns(client, acct)
    except MetaApiError as exc:
        print(f"캠페인 조회 실패: {exc}", flush=True)
        return

    if only_campaign:
        campaigns = [c for c in campaigns if c.get("id") == only_campaign]
    if not campaigns:
        print(
            "캠페인 없음 — Ads Manager에서 이 계정(882)에 소액 캠페인 게재 후 다시 실행.",
            flush=True,
        )
        return

    for c in campaigns:
        cid = c["id"]
        budget = int(c.get("daily_budget") or DAILY_BUDGET_KRW)  # KRW=원 단위(offset=1)
        print(f"\n■ {c.get('name', cid)} [{cid}] effective={c.get('effective_status')}", flush=True)
        try:
            state = await reader.get_state(cid)
            snap = await reader.get_metrics(cid, since)
            print(f"  상태 {state} · {_fmt_metrics(snap)}", flush=True)
            await _run_detection(reader, cid, budget)
        except MetaApiError as exc:
            print(f"  조회 실패: {str(exc)[:160]}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="실 Meta 캠페인 지표·감지 검증")
    parser.add_argument("--since-days", type=int, default=7, help="get_metrics 집계 구간(일)")
    parser.add_argument("--campaign", default=None, help="특정 캠페인 id만 검증")
    args = parser.parse_args()
    asyncio.run(run(args.since_days, args.campaign))


if __name__ == "__main__":
    main()
