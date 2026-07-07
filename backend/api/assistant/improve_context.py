# 시뮬 결과 → 개선모드(IMPROVE) gen_form 프리필 조립 — 채팅 승인·run_improvement 공용
"""도메인 ORM import 없이 raw SQL로 조회한다(api/routers/debate.py의 경계 유지 패턴).

조립(빌더)은 순수 함수로 분리해 DB 없이 테스트한다. product_cutout_s3_key는 '생성한 광고로
시뮬'(ads.generation_id 존재)에 한해 그 generation의 누끼 키를 역추적해 재사용한다 — 그 외엔
None(생성 파이프라인이 null 폴백 지원).
"""

from __future__ import annotations

from sqlalchemy import text

from core.db import AsyncSessionLocal
from tools.storage.s3 import product_cutout_key


def build_sim_summary(aggregate: dict, sample_size: int | None, ad_title: str | None = None) -> str:
    """4대 KPI를 한 줄 요약 — 프론트 buildSimSummary(generator 페이지)와 동일 포맷 유지.

    IMPROVE 요청의 유일한 필수 입력이라 빈 문자열을 반환하지 않는다(제목 폴백).
    """
    parts: list[str] = []
    if sample_size:
        parts.append(f"표본 {sample_size}명")
    pi = aggregate.get("purchase_intent")
    if pi is not None:
        parts.append(f"구매의향 {pi:.2f}/5")
    cir = aggregate.get("click_intent_rate")
    if cir is not None:
        parts.append(f"클릭의향 {round(cir * 100)}%")
    trust = aggregate.get("trust_avg")
    if trust is not None:
        parts.append(f"신뢰도 {trust:.2f}/5")
    rej = aggregate.get("rejection_rate")
    if rej is not None:
        parts.append(f"거부율 {round(rej * 100)}%")
    return " · ".join(parts) or f"{ad_title or '광고'} 시뮬레이션 결과"


def build_improvement_direction(ranked_actions: list[dict]) -> str:
    """토론 ranked_actions → 번호 목록 문자열(프론트와 동일 포맷). 없으면 빈 문자열."""
    lines: list[str] = []
    for i, a in enumerate(ranked_actions):
        action = (a or {}).get("action")
        if not action:
            continue
        effect = (a or {}).get("expected_effect")
        lines.append(f"{i + 1}. {action}{f' — {effect}' if effect else ''}")
    return "\n".join(lines)


def _s3_key_or_none(asset_url: str | None) -> str | None:
    """ads.asset_url은 S3 key/외부 URL/로컬경로 혼재 — 텍스트 힌트로 쓸 수 있는 key만 통과."""
    if not asset_url:
        return None
    u = asset_url.strip()
    if u.startswith(("http://", "https://", "/")) or (len(u) > 1 and u[1] == ":"):
        return None
    return u


def build_improve_gen_data(src: dict, fix_requests: str | None = None) -> dict:
    """조회 소스(fetch_improve_source 결과) → IMPROVE 프리필 gen_form data."""
    return {
        "mode": "improve",
        "product_name": src.get("ad_title") or "",
        "simulation_summary": build_sim_summary(
            src.get("aggregate") or {}, src.get("sample_size"), src.get("ad_title")
        ),
        "plain_summary": src.get("plain_summary"),
        "improvement_direction": build_improvement_direction(src.get("ranked_actions") or []),
        "existing_ad_s3_key": _s3_key_or_none(src.get("ad_asset_url")),
        # 생성한 광고로 시뮬한 경우에만 채워짐(누끼 재사용) — 그 외엔 None(파이프라인 폴백).
        "product_cutout_s3_key": src.get("product_cutout_s3_key"),
        "fix_requests": fix_requests or None,
        "target_audience": "",
        "campaign_objective": "conversion",
    }


async def fetch_improve_source(simulation_id: str, org_id: str | None = None) -> dict | None:
    """시뮬 1건의 개선 재료(제목·원본 이미지·KPI·토론 요약)를 조회. 없거나 미완료면 None."""
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text("""
                    SELECT s.status, s.sample_size,
                           a.title AS ad_title, a.asset_url AS ad_asset_url,
                           a.generation_id,
                           p.organization_id,
                           sa.purchase_intent_avg, sa.rejection_rate, sa.trust_avg,
                           sa.click_intent_rate
                    FROM simulations s
                    JOIN ads a ON a.id = s.ad_id
                    JOIN projects p ON p.id = a.project_id
                    LEFT JOIN simulation_aggregates sa ON sa.simulation_id = s.id
                    WHERE s.id = :sid AND s.deleted_at IS NULL
                """),
                {"sid": simulation_id},
            )
        ).fetchone()
        if row is None or row.status != "COMPLETED":
            return None
        if org_id and row.organization_id is not None and str(row.organization_id) != str(org_id):
            return None

        # 토론 리포트(있으면) — final JSONB에서 plain_summary·ranked_actions만 사용.
        debate = (
            await db.execute(
                text("""
                    SELECT final FROM persona_debates
                    WHERE simulation_id = :sid AND final IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                """),
                {"sid": simulation_id},
            )
        ).fetchone()

        # 상품 누끼 역추적 — 생성한 광고로 시뮬한 경우(generation_id 존재) 그 generation이
        # CREATE + 상품 이미지였으면 누끼가 S3에 있다(get_detail과 동일 게이트). 키를 재구성.
        cutout_key = None
        if row.generation_id is not None:
            g = (
                await db.execute(
                    text("""
                        SELECT input->>'mode' AS mode,
                               input->>'product_image_temp_key' AS product_image_temp_key
                        FROM ad_generations WHERE id = :gid
                    """),
                    {"gid": str(row.generation_id)},
                )
            ).fetchone()
            if g is not None and (g.mode or "create") == "create" and g.product_image_temp_key:
                cutout_key = product_cutout_key(str(row.generation_id))

    final = (debate.final if debate else None) or {}

    def _num(v: object) -> float | None:
        return float(v) if v is not None else None

    return {
        "ad_title": row.ad_title,
        "ad_asset_url": row.ad_asset_url,
        "sample_size": row.sample_size,
        "aggregate": {
            "purchase_intent": _num(row.purchase_intent_avg),
            "rejection_rate": _num(row.rejection_rate),
            "trust_avg": _num(row.trust_avg),
            "click_intent_rate": _num(row.click_intent_rate),
        },
        "plain_summary": final.get("plain_summary"),
        "ranked_actions": final.get("ranked_actions") or [],
        "product_cutout_s3_key": cutout_key,
    }


async def improve_gen_data_for_simulation(
    simulation_id: str, fix_requests: str | None = None, org_id: str | None = None
) -> dict | None:
    """simulation_id → IMPROVE 프리필 gen_form data. 시뮬 없음/미완료/타 org면 None."""
    src = await fetch_improve_source(simulation_id, org_id=org_id)
    if src is None:
        return None
    return build_improve_gen_data(src, fix_requests)


async def latest_completed_simulation_id(project_id: str) -> str | None:
    """프로젝트의 최근 완료 시뮬 id — run_improvement에서 '아까/최근' 자동 선택용."""
    if not project_id:
        return None
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text("""
                    SELECT s.id
                    FROM simulations s
                    JOIN ads a ON a.id = s.ad_id
                    WHERE a.project_id = :pid AND s.deleted_at IS NULL
                          AND s.status = 'COMPLETED'
                    ORDER BY s.created_at DESC
                    LIMIT 1
                """),
                {"pid": project_id},
            )
        ).fetchone()
    return str(row.id) if row else None
