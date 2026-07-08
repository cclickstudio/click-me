# [측정-대비비] base(텍스트 없는) vs 최종 이미지 diff로 텍스트 픽셀을 찾아 WCAG 명도 대비비 집계
r"""텍스트 가독성 개선(적응적 색 선택·최소 밝기 보정, 2026-07-02~06)을 정량화한다.

원리 — 파이프라인이 후보마다 저장하는 '텍스트 없는 base 이미지'와 최종 이미지를
픽셀 diff → 달라진 픽셀(텍스트·버튼·그림자)에 대해 WCAG 상대휘도 대비비를 계산한다.
  ratio = (max(L_final, L_base) + 0.05) / (min(L_final, L_base) + 0.05)

입력 — fetch_generation_images.py가 만든 디렉터리 (manifest의 base_file 사용).
출력 — contrast.csv + 요약 (이미지별 중앙값 대비비, 4.5:1 / 3:1 충족 픽셀 비율).

실행 (backend 디렉터리에서)
  uv run python scripts\measure\measure_contrast.py --dir scripts\measure\out\pipeline
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean, median

from _bootstrap import setup

setup()

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def _relative_luminance(rgb: np.ndarray) -> np.ndarray:
    """sRGB(0~255) → WCAG 상대휘도(0~1). rgb shape (..., 3)."""
    srgb = rgb.astype(np.float64) / 255.0
    linear = np.where(srgb <= 0.03928, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    return linear @ np.array([0.2126, 0.7152, 0.0722])


def _analyze_pair(base_path: Path, final_path: Path, diff_threshold: float) -> dict | None:
    final_img = Image.open(final_path).convert("RGB")
    base_img = Image.open(base_path).convert("RGB")
    if base_img.size != final_img.size:
        base_img = base_img.resize(final_img.size)
    final = np.asarray(final_img)
    base = np.asarray(base_img)

    # 텍스트(오버레이) 픽셀 = base 대비 색이 크게 달라진 픽셀
    color_dist = np.sqrt(((final.astype(np.float64) - base.astype(np.float64)) ** 2).sum(axis=-1))
    mask = color_dist > diff_threshold
    text_pixels = int(mask.sum())
    if text_pixels < final.shape[0] * final.shape[1] * 0.001:
        return None  # 오버레이 영역이 사실상 없음

    lum_final = _relative_luminance(final[mask])
    lum_base = _relative_luminance(base[mask])
    hi = np.maximum(lum_final, lum_base)
    lo = np.minimum(lum_final, lum_base)
    ratios = (hi + 0.05) / (lo + 0.05)

    return {
        "text_pixel_pct": round(text_pixels / mask.size * 100, 2),
        "median_ratio": round(float(np.median(ratios)), 2),
        "p10_ratio": round(float(np.percentile(ratios, 10)), 2),
        "pct_ge_4_5": round(float((ratios >= 4.5).mean() * 100), 1),
        "pct_ge_3_0": round(float((ratios >= 3.0).mean() * 100), 1),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="텍스트 오버레이 WCAG 대비비 측정")
    parser.add_argument("--dir", default=None, help="manifest.json 디렉터리 (base_file 필요)")
    parser.add_argument("--base", default=None, help="단일 쌍 모드 — base 이미지 경로")
    parser.add_argument("--final", default=None, help="단일 쌍 모드 — 최종 이미지 경로")
    parser.add_argument(
        "--diff-threshold",
        type=float,
        default=25.0,
        help="텍스트 픽셀 판정용 색거리 임계 (기본 25)",
    )
    parser.add_argument("--out", default=None, help="CSV 경로 (기본 <dir>/contrast.csv)")
    args = parser.parse_args()

    pairs: list[tuple[str, dict, Path, Path]] = []  # (라벨, manifest entry, base, final)
    if args.base and args.final:
        pairs.append((Path(args.final).name, {}, Path(args.base), Path(args.final)))
        out_path = Path(args.out) if args.out else Path(args.final).parent / "contrast.csv"
    elif args.dir:
        img_dir = Path(args.dir)
        manifest = json.loads((img_dir / "manifest.json").read_text(encoding="utf-8"))
        for e in manifest["items"]:
            if e.get("status") == "ok" and e.get("base_file"):
                pairs.append((e["file"], e, img_dir / e["base_file"], img_dir / e["file"]))
        out_path = Path(args.out) if args.out else img_dir / "contrast.csv"
    else:
        parser.error("--dir 또는 --base/--final 쌍이 필요합니다")
        return

    if not pairs:
        print(
            "base_file이 있는 항목이 없습니다 — "
            "fetch_generation_images.py를 --no-base 없이 실행하세요"
        )
        return

    print(f"대비비 측정 {len(pairs)}쌍 (diff_threshold={args.diff_threshold})")
    rows: list[dict] = []
    for label, entry, base_path, final_path in pairs:
        try:
            stats = _analyze_pair(base_path, final_path, args.diff_threshold)
        except Exception as exc:
            print(f"  {label} — 실패: {exc}")
            continue
        if stats is None:
            print(f"  {label} — 오버레이 픽셀 없음(스킵)")
            continue
        rows.append(
            {
                "file": label,
                "template_id": entry.get("template_id") or "",
                "strategy_type": entry.get("strategy_type") or "",
                **stats,
            }
        )
        print(
            f"  {label} — 중앙값 {stats['median_ratio']}:1, "
            f"4.5:1 충족 {stats['pct_ge_4_5']}%, 3:1 충족 {stats['pct_ge_3_0']}%"
        )

    if not rows:
        print("측정된 쌍이 없습니다")
        return

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n요약 — 이미지 {len(rows)}장")
    print(f"  중앙값 대비비 평균     {mean(r['median_ratio'] for r in rows):.2f}:1")
    print(f"  중앙값 대비비 중앙값   {median(r['median_ratio'] for r in rows):.2f}:1")
    print(f"  4.5:1(WCAG AA) 충족 픽셀 평균  {mean(r['pct_ge_4_5'] for r in rows):.1f}%")
    print(f"  3:1(대형 텍스트) 충족 픽셀 평균  {mean(r['pct_ge_3_0'] for r in rows):.1f}%")
    by_strategy: dict[str, list[float]] = {}
    for r in rows:
        by_strategy.setdefault(r["strategy_type"] or "?", []).append(r["median_ratio"])
    if len(by_strategy) > 1:
        print("  전략별 중앙값 대비비")
        for strategy, vals in sorted(by_strategy.items()):
            print(f"    {strategy:16s} {mean(vals):.2f}:1  (n={len(vals)})")
    print(f"CSV 저장 — {out_path}")


if __name__ == "__main__":
    main()
