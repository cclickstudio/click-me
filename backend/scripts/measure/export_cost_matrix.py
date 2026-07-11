# [측정-비용] cost_matrix 결과를 LangSmith 실집계와 대조 — 우리 추정 vs LangSmith
r"""cost_matrix.py가 남긴 costs.csv의 run_id로 LangSmith 각 run을 조회해,
우리 단가표 추정(est_cost_usd)과 LangSmith가 자체 계산한 비용·토큰을 나란히 비교한다.

- LangSmith는 이미지 모델 단가를 자동 계산하지 못할 수 있어(토큰 기반 모델만) 대조는
  "우리 추정이 맞는지" 교차검증 + 텍스트/토큰 기반 비용의 실측 확인 용도.
- 최종 정답지는 OpenAI/Google 콘솔의 청구 내역(같은 시간대 대조).

실행 (backend 디렉터리에서, cost_matrix.py 실행 후)
  uv run python scripts\measure\export_cost_matrix.py
  uv run python scripts\measure\export_cost_matrix.py --wait 20   # 인제스트 지연 대기
"""

from __future__ import annotations

import argparse
import csv
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean

from _bootstrap import setup

setup()

from langsmith import Client  # noqa: E402

from core.config import settings  # noqa: E402


def _num(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="cost_matrix ↔ LangSmith 비용 대조")
    parser.add_argument("--csv", default="scripts/measure/out/cost_matrix/costs.csv")
    parser.add_argument("--wait", type=int, default=0, help="조회 전 대기 초(인제스트 지연 대비)")
    parser.add_argument("--out", default="scripts/measure/out/cost_matrix/compare.csv")
    args = parser.parse_args()

    if not settings.LANGSMITH_API_KEY:
        print("LANGSMITH_API_KEY(.env)가 비어 있어 LangSmith 대조 불가")
        return
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"costs.csv 없음 — 먼저 cost_matrix.py 실행: {csv_path}")
        return
    if args.wait:
        print(f"LangSmith 인제스트 대기 {args.wait}초")
        time.sleep(args.wait)

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
    client = Client(api_key=settings.LANGSMITH_API_KEY, api_url=settings.LANGSMITH_ENDPOINT)

    enriched: list[dict] = []
    for r in rows:
        est = _num(r.get("est_cost_usd", ""))
        ls_cost = ls_tokens = None
        run_id = (r.get("run_id") or "").strip()
        if run_id:
            try:
                run = client.read_run(run_id)
                ls_cost = float(run.total_cost) if run.total_cost is not None else None
                ls_tokens = run.total_tokens or 0
            except Exception as exc:
                ls_cost, ls_tokens = None, f"read 실패: {type(exc).__name__}"
        enriched.append(
            {
                **r,
                "est_cost_usd": est,
                "ls_cost_usd": ls_cost,
                "ls_tokens": ls_tokens,
            }
        )

    # 조합별 평균 비교
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for e in enriched:
        if e["status"] == "ok":
            groups[(e["profile"], e["op"], e["model"], e["quality"])].append(e)

    print(f"\n조합별 대조 (n=성공건수) — 프로젝트 {settings.LANGSMITH_PROJECT!r}")
    hdr = (
        f"{'P':2s} {'op':16s} {'모델':22s} {'품질':7s} {'n':>2s} "
        f"{'우리추정$':>10s} {'LS비용$':>10s} {'LS토큰':>8s}"
    )
    print(hdr)
    print("-" * len(hdr))
    for key in sorted(groups):
        es = groups[key]
        est_vals = [e["est_cost_usd"] for e in es if isinstance(e["est_cost_usd"], float)]
        ls_vals = [e["ls_cost_usd"] for e in es if isinstance(e["ls_cost_usd"], float)]
        tok_vals = [e["ls_tokens"] for e in es if isinstance(e["ls_tokens"], int)]
        p, op, model, q = key
        est_m = f"{mean(est_vals):.4f}" if est_vals else "-"
        ls_m = f"{mean(ls_vals):.4f}" if ls_vals else "-"
        tok_m = f"{mean(tok_vals):.0f}" if tok_vals else "-"
        print(
            f"{p:2s} {op:16s} {model:22s} {q:7s} {len(es):2d} {est_m:>10s} {ls_m:>10s} {tok_m:>8s}"
        )

    out_path = Path(args.out)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "profile",
                "op",
                "model",
                "quality",
                "rep",
                "status",
                "image_count",
                "est_cost_usd",
                "ls_cost_usd",
                "ls_tokens",
                "latency_sec",
                "run_id",
            ],
        )
        writer.writeheader()
        for e in enriched:
            writer.writerow({k: e.get(k) for k in writer.fieldnames})
    print(f"\n대조 CSV 저장 — {out_path}")
    print(
        "주의 — LangSmith는 이미지 모델 단가를 자동 계산 못 할 수 있어 LS비용$가 0/빈칸이면 "
        "우리 추정(메타 cost_usd)이 유일 근거. 최종 확정은 OpenAI/Google 콘솔 청구 내역과 대조."
    )


if __name__ == "__main__":
    main()
