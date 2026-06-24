# 매니지먼트 실시간 조회 툴 — 답변의 '숫자' 근거 (read-only, Meta 실측)
"""에이전트가 부르는 조회 함수들. 기존 reader/comparison/prediction을 재사용하며 쓰기는 없다.

숫자는 반드시 여기(실측)에서 나온다 — 지식베이스(KB) 문서는 해석·가이드에만 쓴다(환각 방지).
Meta 요청 한도(rate limit)면 {"error":"rate_limited"}로 표면화한다.
"""

from __future__ import annotations

import calendar
from datetime import UTC, datetime

from sqlalchemy import select

from core.db import AsyncSessionLocal
from core.models import CreatedCampaign
from domain.management.adapters.meta.client import MetaApiError
from domain.management.comparison.service.before_after_service import compute_before_after
from domain.management.contracts.schemas import RealOutcome
from domain.management.wiring import build_prediction_reader, build_reader


def _outcome(m, campaign_id: str, creative_id: str | None) -> RealOutcome:
    """MetricsSnapshot → RealOutcome (compute_before_after 입력용)."""
    return RealOutcome(
        creative_id=creative_id,
        campaign_id=campaign_id,
        impressions=m.impressions,
        reach=m.cum_reach,
        spend_krw=m.spend_krw,
        ctr=m.ctr,
        cpc_krw=m.cpc_krw,
        cpm_krw=m.cpm_krw,
        conversions=m.conversions,
        cvr=m.cvr,
        roas=m.roas,
        as_of=m.as_of,
    )


async def live_campaigns(settings) -> dict:
    """캠페인 목록 + 핵심 실측(상태·지출·CTR·ROAS)."""
    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        camps = await reader.list_campaigns()
        items = []
        for c in camps:
            m = await reader.get_metrics(c.campaign_id, now)
            items.append(
                {
                    "campaign_id": c.campaign_id,
                    "name": c.name,
                    "state": str(getattr(c.state, "value", c.state)),
                    "spend_krw": m.spend_krw,
                    "impressions": m.impressions,
                    "clicks": m.clicks,
                    "ctr": m.ctr,
                    "roas": m.roas,
                }
            )
        return {"campaigns": items, "count": len(items)}
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_budget(settings) -> dict:
    """이번 달 소진·런레이트 예측·여력(Meta 선불 잔액)."""
    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        spent = await reader.get_account_spend("this_month")
        funding = await reader.get_account_funding()
        days_in_month = calendar.monthrange(now.year, now.month)[1]
        projection = round(spent / now.day * days_in_month) if now.day and spent else spent
        return {
            "period": now.strftime("%Y-%m"),
            "this_month_spent_krw": spent,
            "runrate_projection_krw": projection,
            "account_balance_krw": funding.available_balance_krw or 0,
        }
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_campaign_detail(settings, campaign_id: str) -> dict:
    """단일 캠페인 실측 + 게재 상태(심사·이슈)."""
    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        m = await reader.get_metrics(campaign_id, now)
        d = await reader.get_delivery_status_detail(campaign_id)
        return {
            "campaign_id": campaign_id,
            "spend_krw": m.spend_krw,
            "impressions": m.impressions,
            "ctr": m.ctr,
            "roas": m.roas,
            "conversions": m.conversions,
            "effective_status": d.effective_status,
            "issues": list(d.issues_info),
        }
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_before_after(settings) -> dict:
    """집행 전(시뮬 예측) vs 후(실측) 방향성 — 캠페인별 verdict."""
    reader = build_reader(settings)
    pred = build_prediction_reader(settings)
    now = datetime.now(UTC)
    creative_by_meta: dict[str, str] = {}
    sim_by_meta: dict[str, tuple[str, str]] = {}
    try:
        async with AsyncSessionLocal() as db:
            rows = (
                (
                    await db.execute(
                        select(CreatedCampaign).where(CreatedCampaign.deleted_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            for r in rows:
                if not r.meta_campaign_id:
                    continue
                if r.creative_ad_id:
                    creative_by_meta[str(r.meta_campaign_id)] = r.creative_ad_id
                if r.simulation_id:
                    sim_by_meta[str(r.meta_campaign_id)] = (str(r.simulation_id), r.tenant_id)
    except Exception:  # noqa: BLE001 — 매핑 실패해도 실측은 보여준다
        creative_by_meta = {}
        sim_by_meta = {}
    try:
        items = []
        for c in await reader.list_campaigns():
            cid = c.campaign_id
            m = await reader.get_metrics(cid, now)
            link = sim_by_meta.get(cid)
            prediction = await pred.get_prediction(link[0], link[1]) if link else None
            ba = compute_before_after(
                cid, c.name, prediction, _outcome(m, cid, creative_by_meta.get(cid))
            )
            items.append({"name": ba.name, "verdict": ba.verdict.value, "rationale": ba.rationale})
        return {"items": items}
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


#: 라우팅 intent → 실시간 툴 (그래프의 retrieve_live가 선택 호출)
INTENT_TOOLS = {
    "campaigns": ("live_campaigns", live_campaigns),
    "budget": ("live_budget", live_budget),
    "before_after": ("live_before_after", live_before_after),
    "campaign_detail": ("live_campaign_detail", live_campaign_detail),
}
