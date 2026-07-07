# [측정-QA] DB의 생성 후보 QA 점수·통과율을 CSV로 추출 — 개선 루프 품질 곡선·모드별 비교 데이터
r"""ad_generations/ad_generation_candidates에서 QA 신호를 뽑아 집계한다.

- 후보 단위 CSV (생성ID·모드·템플릿·전략·qa_passed·평균 품질점수·시각)
- 요약: 전체 QA 통과율·평균 점수, CREATE vs IMPROVE 비교, 템플릿·전략별 평균
- 자동 개선 루프 곡선: 루프가 만든 생성들은 시간순 CREATE→IMPROVE→IMPROVE라
  created_at 순 정렬 CSV에서 iteration별 점수 상승을 그대로 차트로 만들 수 있다

실행 (backend 디렉터리에서)
  uv run python scripts\measure\export_qa_scores.py --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

from _bootstrap import setup

setup()

from sqlalchemy import select  # noqa: E402

from core.db import AsyncSessionLocal  # noqa: E402
from core.models import AdGeneration, AdGenerationCandidate, User  # noqa: E402


def _avg_quality(qa: object) -> float | None:
    """generator_service._candidate_quality와 동일한 평균 산식."""
    if not isinstance(qa, dict):
        return None
    scores = [
        float(v.get("score") or 0.0) for v in qa.values() if isinstance(v, dict) and "score" in v
    ]
    return round(sum(scores) / len(scores), 3) if scores else None


def _group_stats(rows: list[dict], key: str) -> list[tuple[str, int, float, float]]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get(key) or "?"), []).append(r)
    out = []
    for name, rs in sorted(groups.items()):
        scored = [r["quality_score"] for r in rs if r["quality_score"] is not None]
        passed = [r for r in rs if r["qa_passed"]]
        out.append((name, len(rs), len(passed) / len(rs) * 100, mean(scored) if scored else 0.0))
    return out


async def main() -> None:
    parser = argparse.ArgumentParser(description="생성 QA 점수·통과율 추출")
    parser.add_argument("--days", type=int, default=30, help="최근 N일 (기본 30)")
    parser.add_argument("--project-id", default=None, help="프로젝트 필터")
    parser.add_argument("--login-id", default=None, help="내 계정(login_id) 생성분만")
    parser.add_argument("--product-contains", default=None, help="상품명 부분일치 필터")
    parser.add_argument("--out", default="scripts/measure/out/qa_scores.csv")
    args = parser.parse_args()

    since = datetime.now() - timedelta(days=args.days)
    async with AsyncSessionLocal() as session:
        stmt = (
            select(AdGeneration)
            .where(AdGeneration.status == "completed", AdGeneration.created_at >= since)
            .order_by(AdGeneration.created_at)
        )
        if args.project_id:
            stmt = stmt.where(AdGeneration.project_id == uuid.UUID(args.project_id))
        if args.login_id:
            user_id = await session.scalar(select(User.id).where(User.login_id == args.login_id))
            if user_id is None:
                print(f"login_id {args.login_id!r} 사용자를 찾을 수 없습니다")
                return
            stmt = stmt.where(AdGeneration.created_by == user_id)
        if args.product_contains:
            stmt = stmt.where(
                AdGeneration.input["product_name"].astext.ilike(f"%{args.product_contains}%")
            )
        gens = (await session.scalars(stmt)).all()
        if not gens:
            print(f"최근 {args.days}일 완료 생성이 없습니다")
            return

        rows: list[dict] = []
        for gen in gens:
            cands = (
                await session.scalars(
                    select(AdGenerationCandidate)
                    .where(AdGenerationCandidate.generation_id == gen.id)
                    .order_by(AdGenerationCandidate.idx)
                )
            ).all()
            for c in cands:
                rows.append(
                    {
                        "created_at": gen.created_at.isoformat(timespec="seconds"),
                        "generation_id": str(gen.id),
                        "mode": (gen.input or {}).get("mode") or "CREATE",
                        "product_name": (gen.input or {}).get("product_name") or "",
                        "idx": c.idx,
                        "template_id": c.template_id or "",
                        "strategy_type": (c.strategy or {}).get("strategy_type") or "",
                        "qa_passed": bool(c.qa_passed),
                        "quality_score": _avg_quality(c.qa_result),
                    }
                )

    if not rows:
        print("후보가 없습니다")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    scored = [r["quality_score"] for r in rows if r["quality_score"] is not None]
    passed_n = sum(1 for r in rows if r["qa_passed"])
    print(f"요약 — 생성 {len(gens)}건 / 후보 {len(rows)}개 (최근 {args.days}일)")
    print(f"  QA 통과율        {passed_n / len(rows) * 100:.1f}%  ({passed_n}/{len(rows)})")
    if scored:
        print(f"  평균 품질점수    {mean(scored):.3f}")
    for key, label in (
        ("mode", "모드별"),
        ("template_id", "템플릿별"),
        ("strategy_type", "전략별"),
    ):
        stats = _group_stats(rows, key)
        if len(stats) > 1:
            print(f"  {label}")
            for name, n, pass_pct, avg in stats:
                print(f"    {name:16s} n={n:3d}  통과율 {pass_pct:5.1f}%  평균점수 {avg:.3f}")
    print(f"CSV 저장 — {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
