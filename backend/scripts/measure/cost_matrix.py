# [측정-비용] 이미지 모델×품질 단가 매트릭스 — 오메가3 1장으로 모델·품질·op별 실비 측정
r"""이미지 생성 비용을 모델×품질×작업(op) 단위로 실측한다.

두 프로파일을 돈다.
- B_unit(단가)      : 모든 모델을 generate(0부터 생성) 한 op으로 통일 → 모델×품질 순수 단가 비교.
- A_pipeline(실제)  : openai 실제 경로 재현 — remove_background(누끼) + edit_with_mask(인페인팅).
                      gemini는 파이프라인도 generate와 동일해 B_unit으로 갈음(중복 측정 안 함).

각 측정은 LangSmith run(`cost_matrix.*`)으로 태깅되고, core.tracing.record_image_cost가
모델·품질·op·cost_usd를 그 run 메타데이터에 남긴다 → LangSmith에서 그대로 분해·필터 가능.
결과는 out/cost_matrix/costs.csv와 조합별 샘플 PNG로 저장된다.

실행 (backend 디렉터리에서)
  uv run python scripts\measure\cost_matrix.py --reps 3
  uv run python scripts\measure\cost_matrix.py --reps 1 --profiles B   # 스모크(단가만)
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import csv
import os
import time
from datetime import datetime
from pathlib import Path

from _bootstrap import setup

BACKEND_ROOT = setup()

from dotenv import load_dotenv  # noqa: E402

load_dotenv(BACKEND_ROOT / ".env")

from core.config import settings  # noqa: E402

# LangSmith SDK는 os.environ를 읽는다(api/main.py와 동일 패턴) — 명시 세팅해야 업로드된다.
os.environ.setdefault("LANGSMITH_API_KEY", settings.LANGSMITH_API_KEY)
os.environ.setdefault("LANGSMITH_ENDPOINT", settings.LANGSMITH_ENDPOINT)
os.environ.setdefault("LANGSMITH_PROJECT", settings.LANGSMITH_PROJECT)
os.environ["LANGSMITH_TRACING"] = "true" if settings.LANGSMITH_TRACING_V2 else "false"

from langsmith import trace  # noqa: E402

from domain.generator.contracts.enums import AdSize, TemplateType  # noqa: E402
from domain.generator.pipeline import image_providers  # noqa: E402
from domain.generator.pipeline.image_generator import (  # noqa: E402
    _build_inpaint_base_and_mask,
)

# ── 매트릭스 정의 ─────────────────────────────────────────────────────────────
OMEGA3 = Path("scripts/measure/product_images/오메가3.png")
SIZE = AdSize.SQUARE  # 1024x1024 — 단가표와 일치
OPENAI_MODELS = ["gpt-image-1", "gpt-image-2"]
OPENAI_QUALITIES = ["low", "medium", "high"]
GEMINI_MODELS = ["gemini-2.5-flash-image", "gemini-3-pro-image"]

# 배경 생성 프롬프트 — 짧게(비용은 출력 이미지 토큰이 지배, 프롬프트 영향 미미).
BG_PROMPT = (
    "Create a clean, modern e-commerce advertisement background around the product. "
    "Soft studio lighting, minimal, premium. Absolutely no text, letters, or numbers."
)


async def _measure(
    *,
    profile: str,
    model: str,
    quality: str | None,
    op: str,
    rep: int,
    run_ops,
    out_dir: Path,
) -> tuple[dict, list[bytes]]:
    """한 조합을 LangSmith run으로 감싸 측정하고 (row, 생성이미지들)을 반환한다."""
    qlabel = quality or "n/a"
    name = f"cost_matrix.{profile}.{op}.{model}" + (f".{quality}" if quality else "")
    tags = [
        "cost_matrix",
        f"profile:{profile}",
        f"op:{op}",
        f"model:{model}",
        f"quality:{qlabel}",
    ]
    metadata = {
        "profile": profile,
        "op": op,
        "model": model,
        "quality": qlabel,
        "rep": rep,
        "product": "omega3",
    }
    row: dict = {
        "profile": profile,
        "op": op,
        "model": model,
        "quality": qlabel,
        "rep": rep,
        "status": "",
        "image_count": None,
        "est_cost_usd": None,
        "latency_sec": None,
        "run_id": "",
    }
    imgs: list[bytes] = []
    t0 = time.perf_counter()
    with trace(
        name=name,
        run_type="chain",
        tags=tags,
        metadata=metadata,
        project_name=settings.LANGSMITH_PROJECT,
    ) as rt:
        try:
            imgs = await run_ops()
            row["status"] = "ok"
        except Exception as exc:  # 실패(모델 미접근 등)도 데이터 — 기록하고 계속
            row["status"] = f"failed: {type(exc).__name__}: {exc}"[:180]
        meta = (getattr(rt, "extra", None) or {}).get("metadata") or {}
        row["est_cost_usd"] = meta.get("cost_usd")
        row["image_count"] = meta.get("image_count")
        row["run_id"] = str(getattr(rt, "id", "") or "")
    row["latency_sec"] = round(time.perf_counter() - t0, 1)

    if imgs:
        stem = f"{profile}_{op}_{model}_{qlabel}_{rep}".replace(".", "-").replace("/", "-")
        with contextlib.suppress(Exception):
            (out_dir / f"{stem}.png").write_bytes(imgs[0])
    print(
        f"  [{row['status'][:18]:18s}] {name:48s} est=${row['est_cost_usd']} {row['latency_sec']}s"
    )
    return row, imgs


async def _run_profile_b(omega_bytes: bytes, reps: int, out_dir: Path) -> list[dict]:
    """B_unit — 모든 모델을 generate 한 op으로 단가 비교."""
    rows: list[dict] = []

    async def _gen(model: str, provider: str, quality: str | None) -> list[bytes]:
        q = quality or settings.generator_image_quality
        img = await image_providers.generate(
            BG_PROMPT, SIZE, provider=provider, model=model, quality=q
        )
        return [img]

    for model in OPENAI_MODELS:
        for q in OPENAI_QUALITIES:
            for rep in range(reps):
                row, _ = await _measure(
                    profile="B",
                    model=model,
                    quality=q,
                    op="generate",
                    rep=rep,
                    run_ops=lambda m=model, qq=q: _gen(m, "openai", qq),
                    out_dir=out_dir,
                )
                rows.append(row)
    for model in GEMINI_MODELS:
        for rep in range(reps):
            row, _ = await _measure(
                profile="B",
                model=model,
                quality=None,
                op="generate",
                rep=rep,
                run_ops=lambda m=model: _gen(m, "google_genai", None),
                out_dir=out_dir,
            )
            rows.append(row)
    return rows


async def _run_profile_a(omega_bytes: bytes, reps: int, out_dir: Path) -> list[dict]:
    """A_pipeline — openai 실제 경로: 누끼(remove_background) + 인페인팅(edit_with_mask)."""
    rows: list[dict] = []
    for model in OPENAI_MODELS:
        cutout: bytes | None = None

        # 1) 누끼 — 품질 티어별 측정. 재사용할 컷아웃을 여기서 확보(medium 우선).
        async def _cutout(m: str, q: str) -> list[bytes]:
            cut = await image_providers.remove_background(
                omega_bytes, provider="openai", model=m, quality=q
            )
            return [cut]

        for q in OPENAI_QUALITIES:
            for rep in range(reps):
                row, imgs = await _measure(
                    profile="A",
                    model=model,
                    quality=q,
                    op="remove_background",
                    rep=rep,
                    run_ops=lambda m=model, qq=q: _cutout(m, qq),
                    out_dir=out_dir,
                )
                rows.append(row)
                if imgs and (cutout is None or q == "medium"):
                    cutout = imgs[0]

        # 2) 인페인팅 — 위 컷아웃으로 base/mask를 만들어 품질 티어별 측정.
        if cutout is None:
            print(f"  ! {model}: 누끼 컷아웃 확보 실패 — 인페인팅 측정 스킵")
            continue
        base_png, mask_png = _build_inpaint_base_and_mask(cutout, TemplateType.A, SIZE)

        async def _inpaint(m: str, q: str, base=base_png, mask=mask_png) -> list[bytes]:
            img = await image_providers.edit_with_mask(
                base, mask, BG_PROMPT, SIZE, provider="openai", model=m, quality=q
            )
            return [img]

        for q in OPENAI_QUALITIES:
            for rep in range(reps):
                row, _ = await _measure(
                    profile="A",
                    model=model,
                    quality=q,
                    op="edit_with_mask",
                    rep=rep,
                    run_ops=lambda m=model, qq=q: _inpaint(m, qq),
                    out_dir=out_dir,
                )
                rows.append(row)
    return rows


def _write_csv(rows: list[dict], out_dir: Path) -> Path:
    out_path = out_dir / "costs.csv"
    fields = [
        "profile",
        "op",
        "model",
        "quality",
        "rep",
        "status",
        "image_count",
        "est_cost_usd",
        "latency_sec",
        "run_id",
    ]
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def _print_summary(rows: list[dict]) -> None:
    from collections import defaultdict
    from statistics import mean

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["profile"], r["op"], r["model"], r["quality"])].append(r)

    print("\n조합별 평균 (est_cost_usd = 우리 단가표 추정)")
    print(f"{'프로파일':6s} {'op':16s} {'모델':22s} {'품질':7s} {'n':>2s} {'ok':>2s} {'평균$':>9s}")
    total = 0.0
    for key in sorted(groups):
        rs = groups[key]
        ok = [r for r in rs if r["status"] == "ok" and r["est_cost_usd"] is not None]
        avg = mean(r["est_cost_usd"] for r in ok) if ok else 0.0
        total += sum(r["est_cost_usd"] for r in ok)
        p, op, model, q = key
        print(f"{p:6s} {op:16s} {model:22s} {q:7s} {len(rs):2d} {len(ok):2d} {avg:9.4f}")
    print(f"\n측정 총 추정비용 ${total:.4f} (실행된 성공 호출 합계)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="이미지 모델×품질 단가 매트릭스 측정")
    parser.add_argument("--reps", type=int, default=3, help="조합당 반복 횟수 (기본 3)")
    parser.add_argument(
        "--profiles", default="AB", help="측정 프로파일: A(파이프라인)/B(단가)/AB(둘 다, 기본)"
    )
    parser.add_argument("--out", default="scripts/measure/out/cost_matrix")
    args = parser.parse_args()

    if not settings.LANGSMITH_API_KEY:
        print(
            "경고 — LANGSMITH_API_KEY(.env)가 비어 있습니다. "
            "est_cost는 로컬 계산되지만 LangSmith 업로드·대조는 불가합니다."
        )
    if not OMEGA3.exists():
        print(f"오메가3 이미지 없음 — {OMEGA3}")
        return
    omega_bytes = OMEGA3.read_bytes()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    profiles = args.profiles.upper()

    print(
        f"측정 시작 — 오메가3, size={SIZE.value}, reps={args.reps}, profiles={profiles}, "
        f"project={settings.LANGSMITH_PROJECT}"
    )
    rows: list[dict] = []
    if "B" in profiles:
        print("\n[B_unit] generate 단가 매트릭스")
        rows += await _run_profile_b(omega_bytes, args.reps, out_dir)
    if "A" in profiles:
        print("\n[A_pipeline] openai 누끼+인페인팅 실측")
        rows += await _run_profile_a(omega_bytes, args.reps, out_dir)

    csv_path = _write_csv(rows, out_dir)
    _print_summary(rows)
    ok = sum(1 for r in rows if r["status"] == "ok")
    print(f"\n완료 — {ok}/{len(rows)}건 성공, CSV {csv_path}")
    print(
        "다음 — uv run python scripts\\measure\\export_cost_matrix.py  "
        f"(측정 시각 {datetime.now().isoformat(timespec='seconds')})"
    )


if __name__ == "__main__":
    asyncio.run(main())
