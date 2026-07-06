# 잠재고객(리드) 명단 조회 — Meta leadgen에서 캠페인 하위 광고별 리드 수집(화면·챗 공용)
"""리드 데이터는 Meta에 저장된다(우리 도메인 아님). 페이지 토큰 + leads_retrieval 권한이
필요하며, 권한·토큰 문제는 note로 안내한다(빈 목록 반환, 소비자 화면이 안 깨지게).
"""

from __future__ import annotations

from typing import Any

from domain.management.adapters.meta.client import MetaApiError


async def fetch_campaign_leads(settings: Any, campaign_id: str) -> dict:
    """이 캠페인 광고로 제출된 리드 명단 — live 전용(mock이면 안내만)."""
    if getattr(settings, "use_mock", True):
        return {"leads": [], "count": 0, "note": "데모(mock) 모드 — 리드는 live에서 조회됩니다."}
    from domain.management.adapters.meta.client import (  # noqa: PLC0415 — live 전용 지연 로드
        MetaClient,
        build_meta_client,
    )

    client = build_meta_client(settings)
    page_id = str(getattr(settings, "meta_page_id", "") or "")
    try:
        # 사용자 토큰 → 페이지 토큰 (leadgen 리드 조회는 페이지 토큰 필요)
        accts = await client.get("me/accounts", {"fields": "id,access_token", "limit": 100})
        page_token = next(
            (p.get("access_token") for p in accts.get("data", []) if str(p.get("id")) == page_id),
            None,
        )
        if not page_token:
            return {"leads": [], "count": 0, "note": "페이지 토큰을 얻지 못함(페이지 권한 확인)."}
        page_client = MetaClient(
            page_token, api_version=getattr(settings, "meta_graph_api_version", None) or "v21.0"
        )
        # 캠페인 하위 광고 → 광고별 리드 수집
        ads = await client.get(f"{campaign_id}/ads", {"fields": "id", "limit": 200})
        leads: list[dict] = []
        for ad in ads.get("data", []):
            res = await page_client.get(
                f"{ad['id']}/leads", {"fields": "created_time,field_data", "limit": 200}
            )
            for lead in res.get("data", []):
                fields = {
                    f.get("name"): (f.get("values") or [""])[0]
                    for f in (lead.get("field_data") or [])
                }
                leads.append({"created_time": lead.get("created_time"), "fields": fields})
        leads.sort(key=lambda x: x.get("created_time") or "", reverse=True)
        return {"leads": leads, "count": len(leads)}
    except MetaApiError as exc:
        # 권한 부족(leads_retrieval 미승인)·토큰 문제 등 — 소비자용 안내로 변환.
        return {"leads": [], "count": 0, "note": f"리드 조회 불가: {exc.user_msg or exc.message}"}
