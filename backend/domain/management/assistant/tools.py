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
    """캠페인 목록 + 실측 전체 지표(성과비교 화면과 동일 셋)."""
    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        camps = await reader.list_campaigns()
        items = []
        for c in camps:
            m = await reader.get_metrics(c.campaign_id, now)
            # 성과비교(집행 후 · 실측 전체)와 동일 지표: 노출·도달·지출·CTR·CPC·CPM·CVR·ROAS·전환.
            items.append(
                {
                    "campaign_id": c.campaign_id,
                    "name": c.name,
                    "state": str(getattr(c.state, "value", c.state)),
                    "impressions": m.impressions,
                    "reach": m.cum_reach,
                    "clicks": m.clicks,  # 원값 유지 — 채팅 '클릭 수' 질문에 CTR 역산 없이 답하게
                    "spend_krw": m.spend_krw,
                    "ctr": m.ctr,
                    "cpc_krw": m.cpc_krw,
                    "cpm_krw": m.cpm_krw,
                    "cvr": m.cvr,
                    "roas": m.roas,
                    "conversions": m.conversions,
                }
            )
        return {"campaigns": items, "count": len(items)}
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_campaign_find_by_name(settings, name: str) -> dict:
    """캠페인 이름 부분일치(대소문자 무시)로 검색 — campaign_id 해소(live_campaigns 경유).

    캠페인은 Meta live 소스(DB 아님)라 목록을 받아 파이썬 필터. 반환 matches는
    live_campaigns 항목(campaign_id·name·실측)이라 단순 '어느 캠페인?'은 추가 호출 없이 답 가능.
    """
    if not name or not name.strip():
        return {"error": "need_name"}
    res = await live_campaigns(settings)
    if res.get("error"):
        return res
    q = name.strip().casefold()
    matches = [c for c in res.get("campaigns", []) if q in (c.get("name") or "").casefold()]
    return {"query": name.strip(), "matches": matches, "count": len(matches)}


_BUDGET_PRESETS = ("this_month", "last_month")


async def live_budget(settings, date_preset: str = "this_month") -> dict:
    """예산 소진·런레이트(월말 예상)·여력. date_preset='this_month'(기본)·'last_month'.

    이번 달은 경과일 기준 런레이트로 월말 예상 소진을, 지난 달은 완료 기간이라 실지출을 그대로 준다.
    """
    reader = build_reader(settings)
    now = datetime.now(UTC)
    if date_preset not in _BUDGET_PRESETS:
        date_preset = "this_month"
    is_current = date_preset == "this_month"
    try:
        spent = await reader.get_account_spend(date_preset)
        funding = await reader.get_account_funding()
        if is_current:
            days_in_month = calendar.monthrange(now.year, now.month)[1]
            projection = round(spent / now.day * days_in_month) if now.day and spent else spent
            period_label = now.strftime("%Y-%m")
        else:
            # 지난 달 = 이미 종료 → 월말 예상이 아니라 실지출 그대로.
            py, pm = (now.year - 1, 12) if now.month == 1 else (now.year, now.month - 1)
            period_label = f"{py:04d}-{pm:02d}"
            projection = spent
        result = {
            "period": period_label,
            "date_preset": date_preset,
            "spent_krw": spent,
            "runrate_projection_krw": projection,
            "period_complete": not is_current,  # 지난 달이면 projection은 예상 아닌 실지출
            "account_balance_krw": funding.available_balance_krw or 0,
        }
        if is_current:
            result["this_month_spent_krw"] = spent  # 구세대 agent.py 표시 호환
        return result
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_campaign_detail(settings, campaign_id: str) -> dict:
    """단일 캠페인 실측 + 게재 상태(심사·이슈)."""
    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        m = await reader.get_metrics(campaign_id, now)
        d = await reader.get_delivery_status_detail(campaign_id)
        # 성과비교(실측 전체)와 동일 지표 + 게재 상태(심사·이슈).
        return {
            "campaign_id": campaign_id,
            "impressions": m.impressions,
            "reach": m.cum_reach,
            "spend_krw": m.spend_krw,
            "ctr": m.ctr,
            "cpc_krw": m.cpc_krw,
            "cpm_krw": m.cpm_krw,
            "cvr": m.cvr,
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


async def live_weekly_report(settings) -> dict:
    """주간 성과 리포트 — 최근 7일 총합·캠페인별 표·하이라이트(화면 /report/weekly와 동일)."""
    from domain.management.insights import weekly_report  # noqa: PLC0415

    return await weekly_report(build_reader(settings))


async def live_full_report(settings) -> dict:
    """전체 누적 성과 리포트 — 주간과 같은 형식, 기간만 전체(maximum) 실측.

    캠페인이 모두 종료돼 최근 7일이 비는 경우 누적 성과를 봐야 하므로 쓴다.
    """
    from domain.management.insights import weekly_report  # noqa: PLC0415

    return await weekly_report(build_reader(settings), date_preset="maximum")


async def live_rebalance_proposal(settings) -> dict:
    """캠페인 간 일예산 리밸런싱 제안 — 화면 /budget/rebalance-proposal과 동일 로직."""
    from domain.management.insights import rebalance_proposal  # noqa: PLC0415

    return await rebalance_proposal(build_reader(settings))


async def live_organic_compare(settings) -> dict:
    """오가닉 게시물 ↔ 광고 증분 비교 보드(데모 매칭 쌍) — 화면 /compare/board와 동일."""
    _ = settings  # 매칭 쌍 데모라 항상 mock — 시그니처는 다른 live_*와 통일
    from domain.management.insights import organic_ad_board  # noqa: PLC0415

    return await organic_ad_board()


async def live_anomaly_scan(settings, target_roas: float | None = None) -> dict:
    """실 캠페인 성과 이상·노출 피로 스캔 — 이상 있는 캠페인만 반환(live 전용).

    성과 미달 판정은 고객 목표(target_roas)가 있어야 가능하고, 노출 피로(빈도)는 목표 없이도
    잡는다. 화면 /anomaly/scan과 같은 판정 블록(diagnose_performance·FATIGUE_FREQUENCY)을 쓴다.
    """
    if getattr(settings, "use_mock", True):
        return {"scanned": 0, "anomalies": [], "note": "실 캠페인 스캔은 live에서."}
    from domain.management.contracts.enums import (  # noqa: PLC0415
        CampaignState,
        DiagnosisStatus,
    )
    from domain.management.contracts.policy import FATIGUE_FREQUENCY  # noqa: PLC0415
    from domain.management.demo import TENANT_ID  # noqa: PLC0415
    from domain.management.detection.performance_dx import diagnose_performance  # noqa: PLC0415
    from domain.management.wiring import build_diagnosis_agent  # noqa: PLC0415

    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        infos = await reader.list_campaigns()
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}
    anomalies: list[dict] = []
    for c in infos:
        dx_payload = None
        try:
            m = await reader.get_metrics(c.campaign_id, now)
            relevance = await reader.get_relevance_diagnostics(c.campaign_id)
            dx = diagnose_performance(
                TENANT_ID,
                c.campaign_id,
                roas=m.roas,
                target_roas=target_roas,
                as_of=m.as_of,
                relevance=relevance,
            )
            if dx is not None and dx.status == DiagnosisStatus.INCONCLUSIVE:
                dx = await build_diagnosis_agent(settings)(dx, reader)
            if dx is not None:
                dx_payload = {
                    "anomaly_type": dx.anomaly_type.value,
                    "hypothesis": dx.hypothesis,
                    "confidence": dx.confidence,
                }
        except Exception:  # noqa: BLE001 — 캠페인 1건 실패가 전체 스캔을 막지 않게
            dx_payload = None
        if dx_payload:
            anomalies.append(
                {
                    "campaign_id": c.campaign_id,
                    "name": c.name,
                    "state": str(getattr(c.state, "value", c.state)),
                    "diagnosis": dx_payload,
                }
            )
        # 빈도 피로 — 진행 중 캠페인의 최근 7일 빈도가 임계(3.0+)를 넘으면 소재 교체 제안.
        if c.state == CampaignState.ACTIVE:
            try:
                wk = await reader.get_metrics(c.campaign_id, now, date_preset="last_7d")
                freq = wk.frequency or 0.0
            except Exception:  # noqa: BLE001 — 피로 신호 실패는 조용히 건너뜀
                freq = 0.0
            if freq >= FATIGUE_FREQUENCY:
                anomalies.append(
                    {
                        "campaign_id": c.campaign_id,
                        "name": c.name,
                        "state": str(getattr(c.state, "value", c.state)),
                        "diagnosis": {
                            "anomaly_type": "AUDIENCE_FATIGUE",
                            "hypothesis": (
                                f"최근 7일 빈도 {freq:.1f} — 같은 사람에게 반복 노출되는 피로 "
                                f"신호예요(기준 {FATIGUE_FREQUENCY:.0f}+). 소재 교체를 권장합니다."
                            ),
                        },
                        "suggested_action": "REPLACE_CREATIVE",
                    }
                )
    note = None if target_roas else "목표 ROAS 미지정 — 성과 미달 판정은 생략, 피로 신호만 스캔."
    return {"scanned": len(infos), "anomalies": anomalies, "note": note}


async def live_campaign_breakdown(settings, campaign_id: str) -> dict:
    """단일 캠페인 분해 실측 — 게재 플랫폼별(FB/IG) + 연령×성별 노출·클릭·지출·도달."""
    reader = build_reader(settings)
    now = datetime.now(UTC)
    try:
        platforms = await reader.get_platform_breakdown(campaign_id, now)
        demographics = await reader.get_demographic_breakdown(campaign_id, now)
        return {
            "campaign_id": campaign_id,
            "platforms": [r.model_dump(mode="json") for r in platforms],
            "demographics": [r.model_dump(mode="json") for r in demographics],
        }
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_campaign_creatives(settings, campaign_id: str) -> dict:
    """캠페인 대표 크리에이티브 — 광고 시안 이름·썸네일."""
    reader = build_reader(settings)
    try:
        rows = await reader.get_creatives(campaign_id)
        return {"creatives": [r.model_dump(mode="json") for r in rows]}
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_campaign_targeting(settings, campaign_id: str) -> dict:
    """캠페인 타겟팅 설정 — objective·연령·성별(시뮬 사전 입력에도 쓰는 값)."""
    reader = build_reader(settings)
    try:
        return await reader.get_campaign_targeting(campaign_id)
    except MetaApiError as e:
        return {"error": "rate_limited" if e.is_rate_limited else "meta_error", "detail": str(e)}


async def live_campaign_leads(settings, campaign_id: str) -> dict:
    """이 캠페인 광고로 제출된 잠재고객(리드) 명단 — Meta leadgen 조회(live 전용)."""
    from domain.management.leads import fetch_campaign_leads  # noqa: PLC0415

    return await fetch_campaign_leads(settings, campaign_id)


#: 라우팅 intent → 실시간 툴 (그래프의 retrieve_live가 선택 호출)
INTENT_TOOLS = {
    "campaigns": ("live_campaigns", live_campaigns),
    "budget": ("live_budget", live_budget),
    "before_after": ("live_before_after", live_before_after),
    "campaign_detail": ("live_campaign_detail", live_campaign_detail),
}
