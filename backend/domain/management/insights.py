# 주간 성과 리포트·예산 리밸런싱 제안·오가닉 비교 보드 — 결정론 요약(화면·챗 공용 단일 출처)
"""라우터(/report/weekly·/budget/rebalance-proposal·/compare/board)와 챗 어시스턴트 tool이
같은 로직을 공유한다. 전부 reader 실측(비교 보드는 데모 쌍)으로 조립하고 LLM을 쓰지 않아
문구가 항상 재현된다.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from domain.management.campaign_policy import _FALLBACK_FLOOR_KRW, get_campaign_policy
from domain.management.contracts.enums import CampaignState
from domain.management.contracts.policy import (
    FATIGUE_FREQUENCY,
    REBALANCE_CPC_GAP,
    REBALANCE_HIGH_UTIL,
    REBALANCE_LOW_UTIL,
    REBALANCE_MIN_MOVE_KRW,
    REBALANCE_STEP_PCT,
)

# 데모 보드 — (게시물 제목, 오가닉 post id, 광고 campaign id, 일예산). 예산 차이로
# 광고 도달이 벌어져 통과/주의/미달이 고루 나오게 구성.
BOARD_DEMO: tuple[tuple[str, str, str, int], ...] = (
    ("여름 신상 원피스 🌴", "ig_demo_1", "camp_demo_1", 200_000),
    ("브랜드 데일리 룩", "ig_demo_2", "camp_demo_2", 120_000),
    ("신상 액세서리 모음", "ig_demo_3", "camp_demo_3", 40_000),
    ("쿠폰 안내 공지", "ig_demo_4", "camp_demo_4", 15_000),
)


async def weekly_report(reader: Any, date_preset: str = "last_7d") -> dict:
    """성과 리포트 — 기간(date_preset) 실측 총합·캠페인별 표·하이라이트·다음 액션(결정론 요약).

    date_preset='last_7d'(주간, 기본)·'maximum'(누적 전체) 등 — 기간만 다르고 형식은 동일.
    종료된 캠페인은 최근 7일이 비므로 maximum(누적 전체)이 유의미하다.
    """
    now = datetime.now(UTC)
    is_full = date_preset == "maximum"
    span_label = "전체 누적" if is_full else "최근 7일"
    try:
        infos = await reader.list_campaigns()
    except Exception as exc:  # noqa: BLE001
        return {"report": None, "note": getattr(exc, "user_msg", None) or str(exc)}
    rows: list[dict] = []
    for c in infos:
        try:
            m = await reader.get_metrics(c.campaign_id, now, date_preset=date_preset)
        except TypeError:  # mock 등 date_preset 미지원 — 전체 기간 폴백
            try:
                m = await reader.get_metrics(c.campaign_id, now)
            except Exception:  # noqa: BLE001
                continue
        except Exception:  # noqa: BLE001 — 1건 실패가 리포트를 막지 않게
            continue
        rows.append(
            {
                "campaign_id": c.campaign_id,
                "name": c.name,
                "state": c.state.value,
                "spend_krw": getattr(m, "spend_krw", 0) or 0,
                "impressions": getattr(m, "impressions", 0) or 0,
                "clicks": getattr(m, "clicks", 0) or 0,
                "conversions": getattr(m, "conversions", None),
                "ctr": getattr(m, "ctr", 0.0) or 0.0,
                "cpc_krw": getattr(m, "cpc_krw", 0) or 0,
                "frequency": getattr(m, "frequency", 0.0) or 0.0,
            }
        )
    spent = sum(r["spend_krw"] for r in rows)
    imps = sum(r["impressions"] for r in rows)
    clicks = sum(r["clicks"] for r in rows)
    convs = sum(r["conversions"] or 0 for r in rows)
    active_rows = [r for r in rows if r["spend_krw"] > 0]
    highlights: list[str] = []
    if active_rows:
        top = max(active_rows, key=lambda r: r["ctr"])
        highlights.append(f"CTR 1위는 '{top['name']}' ({top['ctr'] * 100:.1f}%)")
        pricey = max(active_rows, key=lambda r: r["cpc_krw"])
        if len(active_rows) >= 2 and pricey["campaign_id"] != top["campaign_id"]:
            highlights.append(
                f"클릭 단가가 가장 비싼 캠페인은 '{pricey['name']}' (₩{pricey['cpc_krw']:,})"
            )
    fatigued = [r for r in rows if r["frequency"] >= FATIGUE_FREQUENCY]
    next_actions: list[str] = []
    for r in fatigued:
        next_actions.append(
            f"'{r['name']}' 빈도 {r['frequency']:.1f} — 소재 교체 검토(이상 감지 참조)"
        )
    if spent == 0:
        next_actions.append(
            f"{span_label} 집행 실적이 없어요 — 새 캠페인 집행 또는 게재 재개를 검토하세요."
        )
    if len(active_rows) >= 2:
        next_actions.append("캠페인 간 효율 차이는 예산 관리의 리밸런싱 제안에서 확인하세요.")
    return {
        "report": {
            "period": {
                "preset": date_preset,
                "label": span_label,
                # 전체 누적(maximum)은 시작일이 계정 개시일이라 고정 표기하지 않는다.
                "since": None if is_full else (now - timedelta(days=7)).date().isoformat(),
                "until": now.date().isoformat(),
            },
            "totals": {
                "spend_krw": spent,
                "impressions": imps,
                "clicks": clicks,
                "conversions": convs,
                "ctr": round(clicks / imps, 4) if imps else 0.0,
                "cpc_krw": round(spent / clicks) if clicks else 0,
            },
            "campaigns": sorted(rows, key=lambda r: r["spend_krw"], reverse=True),
            "highlights": highlights,
            "next_actions": next_actions,
        },
        "note": None,
    }


def _single_adjust_proposal(c: Any, cpc: int, spend_7d: int, floor: int) -> dict:
    """캠페인 1개일 때 — 그 캠페인 자체의 일예산을 소진율(7일 예산 활용도) 기준 증액/감액 제안.

    옮길 상대가 없으므로 '이전'이 아니라 '단일 조정'. 소진율 높으면(예산 한도에 자주 걸림)
    증액, 낮으면(예산이 게재보다 큼) 감액. 적정 범위면 제안하지 않는다(임계=policy.py).
    """
    budget = c.daily_budget_krw
    if budget <= 0:
        return {"proposal": None, "note": "일예산이 설정된 캠페인만 조정을 제안해요."}
    util = spend_7d / (budget * 7)  # 최근 7일 일예산 대비 실지출 = 소진율(기간 평균)
    step = int(budget * REBALANCE_STEP_PCT) // 100 * 100  # 20%, 백원 단위 절사
    if util >= REBALANCE_HIGH_UTIL:
        move = step
        if move < REBALANCE_MIN_MOVE_KRW:
            return {"proposal": None, "note": "조정 가능한 금액이 너무 작아 제안하지 않아요."}
        direction, after = "increase", budget + move
        reason = (
            f"최근 7일 일예산의 {util * 100:.0f}%를 소진했어요(CPC {cpc:,}원). 예산 한도에 자주 "
            "걸려 수요를 놓치고 있을 수 있어, 일예산 20% 증액을 제안해요."
        )
    elif util <= REBALANCE_LOW_UTIL:
        move = min(step, budget - floor)  # 최소예산 아래로 내려가지 않게
        if move < REBALANCE_MIN_MOVE_KRW:
            return {"proposal": None, "note": "이미 최소 일예산에 가까워 감액을 제안하지 않아요."}
        direction, after = "decrease", budget - move
        reason = (
            f"최근 7일 일예산의 {util * 100:.0f}%만 소진했어요(CPC {cpc:,}원). "
            "예산이 실제 게재보다 커서, 일예산 20% 감액으로 적정화를 제안해요."
        )
    else:
        return {
            "proposal": None,
            "note": f"일예산 소진율({util * 100:.0f}%)이 적정 범위라 조정 제안이 없어요.",
        }
    return {
        "proposal": {
            "kind": "adjust",
            "direction": direction,
            "campaign": {
                "campaign_id": c.campaign_id,
                "name": c.name,
                "cpc_krw": cpc,
                "daily_budget_krw": budget,
                "after_krw": after,
            },
            "move_krw": move,
            "basis": "last_7d",
            "reason": reason,
        },
        "note": None,
    }


async def rebalance_proposal(reader: Any) -> dict:
    """일예산 리밸런싱 제안(하이브리드) — 최근 7일 실측 기준, 실행 아닌 '제안'만.

    - 캠페인 **2개 이상**: 저효율(높은 CPC)→고효율(낮은 CPC)로 20% **이전**(kind=transfer).
      CPC 격차가 1.2배 초과일 때만(작은 차이로 예산을 흔들지 않게).
    - 캠페인 **1개**: 옮길 상대가 없어 그 캠페인 자체 일예산을 소진율 기준 **증액/감액**
      (kind=adjust). 적정 범위면 제안 없음.

    적용은 기존 budget-commit(검증·승인·감사 경로) — 자동 집행 없음(HITL 유지).
    """
    now = datetime.now(UTC)
    try:
        infos = await reader.list_campaigns()
    except Exception as exc:  # noqa: BLE001 — 제안은 부가 기능, 조회 실패는 안내로
        return {"proposal": None, "note": getattr(exc, "user_msg", None) or str(exc)}
    elig = [
        c
        for c in infos
        if c.state == CampaignState.ACTIVE and c.budget_type == "daily" and c.daily_budget_krw > 0
    ]
    if not elig:
        return {"proposal": None, "note": "진행 중(일예산형) 캠페인이 있으면 제안해요."}
    rows = []  # (campaign, cpc, spend_7d)
    for c in elig:
        try:
            m = await reader.get_metrics(c.campaign_id, now, date_preset="last_7d")
        except TypeError:  # mock 등 date_preset 미지원 리더 — 전체 기간으로 폴백
            try:
                m = await reader.get_metrics(c.campaign_id, now)
            except Exception:  # noqa: BLE001
                continue
        except Exception:  # noqa: BLE001 — 캠페인 1건 실패가 전체 제안을 막지 않게
            continue
        clicks = getattr(m, "clicks", 0) or 0
        spend = getattr(m, "spend_krw", 0) or 0
        if clicks <= 0 or spend <= 0:
            continue
        cpc = getattr(m, "cpc_krw", 0) or round(spend / clicks)
        rows.append((c, cpc, spend))
    if not rows:
        return {"proposal": None, "note": "최근 실측 클릭이 있는 캠페인이 있으면 제안해요."}
    floor = _FALLBACK_FLOOR_KRW
    try:
        policy = await get_campaign_policy(reader)
        floor = int(policy.get("min_daily_budget_krw") or floor)
    except Exception:  # noqa: BLE001 — 정책 조회 실패 시 보수 폴백
        pass
    # 캠페인 1개 — 단일 조정(증액/감액).
    if len(rows) == 1:
        c, cpc, spend = rows[0]
        return _single_adjust_proposal(c, cpc, spend, floor)
    # 캠페인 2개+ — 저효율→고효율 이전.
    rows.sort(key=lambda r: r[1])
    (best, best_cpc, _), (worst, worst_cpc, _) = rows[0], rows[-1]
    if worst_cpc <= best_cpc * REBALANCE_CPC_GAP:
        return {"proposal": None, "note": "캠페인 간 CPC 격차가 1.2배를 넘으면 이동을 제안해요."}
    move = int(worst.daily_budget_krw * REBALANCE_STEP_PCT) // 100 * 100  # 20%, 백원 단위 절사
    move = min(move, worst.daily_budget_krw - floor)  # 저효율도 최소예산 아래로 안 내려가게
    if move < REBALANCE_MIN_MOVE_KRW:
        return {"proposal": None, "note": "이동 가능한 금액이 너무 작아 제안하지 않아요."}
    return {
        "proposal": {
            "kind": "transfer",
            "from": {
                "campaign_id": worst.campaign_id,
                "name": worst.name,
                "cpc_krw": worst_cpc,
                "daily_budget_krw": worst.daily_budget_krw,
                "after_krw": worst.daily_budget_krw - move,
            },
            "to": {
                "campaign_id": best.campaign_id,
                "name": best.name,
                "cpc_krw": best_cpc,
                "daily_budget_krw": best.daily_budget_krw,
                "after_krw": best.daily_budget_krw + move,
            },
            "move_krw": move,
            "basis": "last_7d",
            "reason": (
                f"최근 7일 CPC가 {worst_cpc:,}원으로 {best.name}({best_cpc:,}원)의 "
                f"{worst_cpc / best_cpc:.1f}배예요. 일예산의 20%를 효율 좋은 쪽으로 옮기면 "
                "같은 돈으로 더 많은 클릭을 살 수 있어요."
            ),
        },
        "note": None,
    }


async def organic_ad_board() -> dict:
    """여러 게시물의 오가닉→광고 증분 일괄 검증 + 권고 (B 뷰). 매칭 쌍 데모라 항상 mock."""
    from domain.management.adapters.mock import MockAdPlatform, MockOrganicReader  # noqa: PLC0415
    from domain.management.comparison.service.comparison_service import (  # noqa: PLC0415
        ComparisonService,
    )

    organic_reader = MockOrganicReader()  # 데모 게시물 — 실모드에도 mock(실 Meta엔 해당 ID 없음)
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    rows = []
    for title, post_id, campaign_id, budget in BOARD_DEMO:
        svc = ComparisonService(organic_reader, MockAdPlatform(daily_budget_krw=budget))
        report = await svc.compare_and_recommend(post_id, campaign_id, since)
        rows.append(
            {
                "title": title,
                "lift": report.lift.model_dump(mode="json"),
                "recommendation": report.recommendation.model_dump(mode="json"),
            }
        )
    return {"rows": rows}
