# [측정-비용] LangSmith 루트 런의 토큰·비용을 집계 — 생성 1회당 평균 토큰/비용 산출
r"""LangSmith에 기록된 트레이스에서 토큰·비용을 뽑아 CSV와 요약을 만든다.

- 루트 런 기준(1 트레이스 = 파이프라인 1회)으로 프롬프트/컴플리션 토큰·비용 합계를 집계
- --name-contains로 특정 파이프라인만 필터 (예: generation)
- 이미지 모델 비용은 core/tracing.record_image_cost가 run에 부착한 값이 total_cost에 포함됨

실행 (backend 디렉터리에서)
  uv run python scripts\measure\export_langsmith_costs.py --days 7
  uv run python scripts\measure\export_langsmith_costs.py --days 7 --name-contains gen
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

from _bootstrap import setup

setup()

from langsmith import Client  # noqa: E402

from core.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="LangSmith 토큰·비용 집계")
    parser.add_argument("--days", type=int, default=7, help="최근 N일 (기본 7)")
    parser.add_argument(
        "--project", default=None, help="프로젝트명 (기본: settings.LANGSMITH_PROJECT)"
    )
    parser.add_argument("--name-contains", default=None, help="런 이름 부분일치 필터 (소문자 비교)")
    parser.add_argument("--limit", type=int, default=500, help="최대 런 수 (기본 500)")
    parser.add_argument("--out", default="scripts/measure/out/langsmith_costs.csv")
    args = parser.parse_args()

    if not settings.LANGSMITH_API_KEY:
        print("LANGSMITH_API_KEY(.env)가 비어 있습니다 — 집계 불가")
        return
    project = args.project or settings.LANGSMITH_PROJECT
    client = Client(api_key=settings.LANGSMITH_API_KEY, api_url=settings.LANGSMITH_ENDPOINT)

    print(f"프로젝트 {project!r} 최근 {args.days}일 루트 런 조회 중")
    runs = client.list_runs(
        project_name=project,
        is_root=True,
        start_time=datetime.now() - timedelta(days=args.days),
        limit=args.limit,
    )

    rows: list[dict] = []
    for run in runs:
        name = run.name or "?"
        if args.name_contains and args.name_contains.lower() not in name.lower():
            continue
        latency = None
        if run.end_time and run.start_time:
            latency = round((run.end_time - run.start_time).total_seconds(), 1)
        rows.append(
            {
                "run_id": str(run.id),
                "name": name,
                "start_time": run.start_time.isoformat(timespec="seconds")
                if run.start_time
                else "",
                "latency_sec": latency,
                "prompt_tokens": run.prompt_tokens or 0,
                "completion_tokens": run.completion_tokens or 0,
                "total_tokens": run.total_tokens or 0,
                "prompt_cost_usd": float(run.prompt_cost or 0),
                "completion_cost_usd": float(run.completion_cost or 0),
                "total_cost_usd": float(run.total_cost or 0),
                "status": run.status,
            }
        )
    if not rows:
        print("조건에 맞는 런이 없습니다 — --name-contains/--days를 조정해보세요")
        return

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    by_name: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_name[r["name"]].append(r)
    print(f"\n요약 — 루트 런 {len(rows)}건 (트레이스당 = 파이프라인 1회)")
    print(f"{'런 이름':30s} {'건수':>4s} {'평균토큰':>10s} {'평균비용$':>10s} {'평균지연s':>9s}")
    for name, rs in sorted(by_name.items(), key=lambda kv: -len(kv[1])):
        avg_tokens = mean(r["total_tokens"] for r in rs)
        avg_cost = mean(r["total_cost_usd"] for r in rs)
        lat = [r["latency_sec"] for r in rs if r["latency_sec"] is not None]
        avg_lat = mean(lat) if lat else 0
        print(f"{name[:30]:30s} {len(rs):4d} {avg_tokens:10.0f} {avg_cost:10.4f} {avg_lat:9.1f}")
    total_cost = sum(r["total_cost_usd"] for r in rows)
    print(f"\n총 비용 ${total_cost:.4f} / 총 토큰 {sum(r['total_tokens'] for r in rows):,}")
    print(f"CSV 저장 — {out_path}")


if __name__ == "__main__":
    main()
