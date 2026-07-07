"""대시보드 집계 API — role별 스코프(ADMIN 전체 / COMPANY 조직 / USER 팀·본인)."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user, user_org_id
from core.db import get_db
from core.models import User

router = APIRouter()


class DashboardStats(BaseModel):
    total_simulations: int
    total_generations: int
    avg_purchase_intent: float | None


class RecentSimulation(BaseModel):
    id: str
    ad_id: str
    ad_title: str | None
    persona_count: int
    avg_intent: float | None
    status: str
    created_at: datetime


class RecentGeneration(BaseModel):
    id: str
    status: str
    product_name: str | None
    mode: str  # create | improve (input JSONB에서 읽음)
    format: str  # single | carousel(카드뉴스) — 생성/카드 배지 분기
    created_at: datetime


async def _project_scope(user: User, db: AsyncSession) -> tuple[str, dict] | None:
    """비-ADMIN 카운트 스코프 — projects 별칭 p 기준 WHERE 절과 파라미터.

    COMPANY=조직 전체, USER=자기 팀(팀 미배정이면 본인 생성 프로젝트). access.py project_access_ok와
    동일한 접근 경계라 "보이는 것 = 세는 것"이 맞는다. COMPANY가 조직 없으면 None(빈 결과).
    """
    role = user.role.upper()
    if role == "COMPANY":
        org_id = await user_org_id(user, db)
        if org_id is None:
            return None
        return "p.organization_id = :org", {"org": str(org_id)}
    # USER
    if user.team_id is not None:
        return "p.team_id = :team", {"team": str(user.team_id)}
    return "p.created_by = :uid", {"uid": str(user.id)}


@router.get("/stats", response_model=DashboardStats)
async def get_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    is_admin = user.role.upper() == "ADMIN"
    if is_admin:
        total_sim = await db.scalar(
            text("SELECT count(*) FROM simulations WHERE deleted_at IS NULL")
        )
        total_gen = await db.scalar(
            text("SELECT count(*) FROM ad_generations WHERE deleted_at IS NULL")
        )
        avg_intent = await db.scalar(
            text("SELECT AVG(purchase_intent_avg) FROM simulation_aggregates")
        )
    else:
        scope = await _project_scope(user, db)
        if scope is None:
            return DashboardStats(
                total_simulations=0, total_generations=0, avg_purchase_intent=None
            )
        clause, params = scope
        total_sim = await db.scalar(
            text(
                f"""
                SELECT count(*) FROM simulations s
                JOIN ads a ON a.id = s.ad_id
                JOIN projects p ON p.id = a.project_id
                WHERE s.deleted_at IS NULL AND {clause}
                """
            ),
            params,
        )
        total_gen = await db.scalar(
            text(
                f"""
                SELECT count(*) FROM ad_generations g
                JOIN projects p ON p.id = g.project_id
                WHERE g.deleted_at IS NULL AND {clause}
                """
            ),
            params,
        )
        avg_intent = await db.scalar(
            text(
                f"""
                SELECT AVG(sa.purchase_intent_avg) FROM simulation_aggregates sa
                JOIN simulations s ON s.id = sa.simulation_id
                JOIN ads a ON a.id = s.ad_id
                JOIN projects p ON p.id = a.project_id
                WHERE s.deleted_at IS NULL AND {clause}
                """
            ),
            params,
        )

    return DashboardStats(
        total_simulations=total_sim or 0,
        total_generations=total_gen or 0,
        avg_purchase_intent=round(float(avg_intent), 2) if avg_intent is not None else None,
    )


@router.get("/recent-simulations", response_model=list[RecentSimulation])
async def get_recent_simulations(
    limit: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ADMIN은 전역, 그 외는 role 스코프(조직/팀/본인). 스코프 없으면 빈 결과.
    is_admin = user.role.upper() == "ADMIN"
    where_extra = ""
    params: dict = {"limit": limit}
    if not is_admin:
        scope = await _project_scope(user, db)
        if scope is None:
            return []
        clause, scope_params = scope
        where_extra = f" AND {clause}"
        params.update(scope_params)
    rows = await db.execute(
        text(
            f"""
            SELECT s.id, s.ad_id, s.sample_size, s.status, s.created_at,
                   a.title AS ad_title, sa.purchase_intent_avg
            FROM simulations s
            JOIN ads a ON a.id = s.ad_id
            JOIN projects p ON p.id = a.project_id
            LEFT JOIN simulation_aggregates sa ON sa.simulation_id = s.id
            WHERE s.deleted_at IS NULL{where_extra}
            ORDER BY s.created_at DESC
            LIMIT :limit
            """
        ),
        params,
    )
    return [
        RecentSimulation(
            id=str(r.id),
            ad_id=str(r.ad_id),
            ad_title=r.ad_title,
            persona_count=r.sample_size,
            avg_intent=round(float(r.purchase_intent_avg), 2)
            if r.purchase_intent_avg is not None
            else None,
            status=r.status,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/recent-generations", response_model=list[RecentGeneration])
async def get_recent_generations(
    limit: int = 5,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ADMIN은 전역, 그 외는 role 스코프(조직/팀/본인). 스코프 없으면 빈 결과.
    is_admin = user.role.upper() == "ADMIN"
    join_sql = ""
    where_extra = ""
    params: dict = {"limit": limit}
    if not is_admin:
        scope = await _project_scope(user, db)
        if scope is None:
            return []
        clause, scope_params = scope
        join_sql = "JOIN projects p ON p.id = g.project_id"
        where_extra = f" AND {clause}"
        params.update(scope_params)
    rows = await db.execute(
        text(
            f"""
            SELECT g.id, g.status, g.input, g.created_at
            FROM ad_generations g
            {join_sql}
            WHERE g.deleted_at IS NULL{where_extra}
            ORDER BY g.created_at DESC
            LIMIT :limit
            """
        ),
        params,
    )
    return [
        RecentGeneration(
            id=str(r.id),
            status=r.status,
            product_name=(r.input or {}).get("product_name"),
            mode=(r.input or {}).get("mode", "create"),
            format=(r.input or {}).get("format", "single"),
            created_at=r.created_at,
        )
        for r in rows
    ]


# ── 대시보드 요약(신규, append-only) — KPI 델타 + 주간 추이 ──────────────
# 프론트 개편(P2)용. 기존 /stats·/recent-* 는 그대로 두고 여기서만 추가 집계를 제공한다.
# 활동 피드는 프론트가 recent-simulations/recent-generations를 병합해 구성(추가 쿼리 불필요).


class WeeklyPoint(BaseModel):
    label: str  # 주 시작일 'M/D'
    simulations: int
    generations: int


class DashboardSummary(BaseModel):
    sims_total: int
    sims_this_week: int
    sims_prev_week: int
    gens_total: int
    gens_this_week: int
    gens_prev_week: int
    avg_purchase_intent: float | None  # 1~5
    avg_click_intent_rate: float | None  # 0~1
    weekly_trend: list[WeeklyPoint]  # 최근 8주(오래된→최신)


@router.get("/summary", response_model=DashboardSummary)
async def get_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """역할 스코프(ADMIN 전체 / COMPANY 조직 / USER 팀·본인) 요약.

    KPI 델타(이번 주 vs 지난 주)와 최근 8주 시뮬/생성 추이를 반환한다.
    """
    is_admin = user.role.upper() == "ADMIN"
    sim_join = ""
    gen_join = ""
    sim_scope = ""
    gen_scope = ""
    params: dict = {}
    if not is_admin:
        scope = await _project_scope(user, db)
        if scope is None:
            return DashboardSummary(
                sims_total=0,
                sims_this_week=0,
                sims_prev_week=0,
                gens_total=0,
                gens_this_week=0,
                gens_prev_week=0,
                avg_purchase_intent=None,
                avg_click_intent_rate=None,
                weekly_trend=[],
            )
        clause, params = scope
        sim_join = "JOIN ads a ON a.id = s.ad_id JOIN projects p ON p.id = a.project_id"
        gen_join = "JOIN projects p ON p.id = g.project_id"
        sim_scope = f" AND {clause}"
        gen_scope = f" AND {clause}"

    # 시뮬 KPI(총계·이번주·지난주·평균 지표)
    sim_row = (
        await db.execute(
            text(
                f"""
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE s.created_at >= date_trunc('week', now())) AS this_week,
                  count(*) FILTER (
                    WHERE s.created_at >= date_trunc('week', now()) - interval '7 days'
                      AND s.created_at < date_trunc('week', now())
                  ) AS prev_week,
                  AVG(sa.purchase_intent_avg) AS avg_pi,
                  AVG(sa.click_intent_rate) AS avg_ci
                FROM simulations s
                LEFT JOIN simulation_aggregates sa ON sa.simulation_id = s.id
                {sim_join}
                WHERE s.deleted_at IS NULL{sim_scope}
                """
            ),
            params,
        )
    ).one()

    # 생성 KPI(총계·이번주·지난주)
    gen_row = (
        await db.execute(
            text(
                f"""
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE g.created_at >= date_trunc('week', now())) AS this_week,
                  count(*) FILTER (
                    WHERE g.created_at >= date_trunc('week', now()) - interval '7 days'
                      AND g.created_at < date_trunc('week', now())
                  ) AS prev_week
                FROM ad_generations g
                {gen_join}
                WHERE g.deleted_at IS NULL{gen_scope}
                """
            ),
            params,
        )
    ).one()

    # 최근 8주 주간 버킷 — DB의 주 시작(월요일) 기준으로 정렬해 프론트 추이 차트에 사용.
    week_start = await db.scalar(text("SELECT date_trunc('week', now())"))
    buckets = [(week_start - timedelta(weeks=7 - i)).date() for i in range(8)]
    since = buckets[0]

    sim_weeks = {
        r.wk.date(): r.c
        for r in await db.execute(
            text(
                f"""
                SELECT date_trunc('week', s.created_at) AS wk, count(*) AS c
                FROM simulations s
                {sim_join}
                WHERE s.deleted_at IS NULL AND s.created_at >= :since{sim_scope}
                GROUP BY wk
                """
            ),
            {**params, "since": since},
        )
    }
    gen_weeks = {
        r.wk.date(): r.c
        for r in await db.execute(
            text(
                f"""
                SELECT date_trunc('week', g.created_at) AS wk, count(*) AS c
                FROM ad_generations g
                {gen_join}
                WHERE g.deleted_at IS NULL AND g.created_at >= :since{gen_scope}
                GROUP BY wk
                """
            ),
            {**params, "since": since},
        )
    }

    weekly_trend = [
        WeeklyPoint(
            label=f"{d.month}/{d.day}",
            simulations=int(sim_weeks.get(d, 0)),
            generations=int(gen_weeks.get(d, 0)),
        )
        for d in buckets
    ]

    return DashboardSummary(
        sims_total=int(sim_row.total or 0),
        sims_this_week=int(sim_row.this_week or 0),
        sims_prev_week=int(sim_row.prev_week or 0),
        gens_total=int(gen_row.total or 0),
        gens_this_week=int(gen_row.this_week or 0),
        gens_prev_week=int(gen_row.prev_week or 0),
        avg_purchase_intent=round(float(sim_row.avg_pi), 2) if sim_row.avg_pi is not None else None,
        avg_click_intent_rate=round(float(sim_row.avg_ci), 4)
        if sim_row.avg_ci is not None
        else None,
        weekly_trend=weekly_trend,
    )
