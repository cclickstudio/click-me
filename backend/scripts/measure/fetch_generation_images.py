# [측정-수집] DB·S3에서 생성 결과(최종본+텍스트 없는 base)를 내려받아 측정용 manifest 구성
r"""현행 파이프라인(after) 이미지를 측정 스크립트 입력 형식으로 수집한다.

- 최종 이미지 + 텍스트 없는 base 이미지(candidate_base_key)를 함께 내려받아
  measure_text_accuracy.py(오타율)·measure_contrast.py(대비비) 입력을 한 번에 만든다.
- 카피(headline/body/cta)·QA 점수·템플릿·전략을 manifest에 동봉한다.

실행 (backend 디렉터리에서)
  uv run python scripts\measure\fetch_generation_images.py --latest 10
  uv run python scripts\measure\fetch_generation_images.py --generation-id <uuid> <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path

from _bootstrap import setup

setup()

from sqlalchemy import select  # noqa: E402

from core.db import AsyncSessionLocal  # noqa: E402
from core.models import AdGeneration, AdGenerationCandidate, User  # noqa: E402
from tools.storage.s3 import candidate_base_key, download_bytes  # noqa: E402


def _avg_quality(qa: object) -> float | None:
    """generator_service._candidate_quality와 동일한 평균 산식 (QA 항목 score 평균)."""
    if not isinstance(qa, dict):
        return None
    scores = [
        float(v.get("score") or 0.0) for v in qa.values() if isinstance(v, dict) and "score" in v
    ]
    return round(sum(scores) / len(scores), 3) if scores else None


async def _fetch_generation(
    session, gen: AdGeneration, out_dir: Path, with_base: bool
) -> list[dict]:
    gid = str(gen.id)
    cands = (
        await session.scalars(
            select(AdGenerationCandidate)
            .where(AdGenerationCandidate.generation_id == gen.id)
            .order_by(AdGenerationCandidate.idx)
        )
    ).all()
    entries: list[dict] = []
    for c in cands:
        if not c.s3_key:
            continue
        stem = f"{gid[:8]}_c{c.idx}"
        entry: dict = {
            "file": f"{stem}.png",
            "method": "pipeline",
            "generation_id": gid,
            "idx": c.idx,
            "mode": (gen.input or {}).get("mode"),
            "template_id": c.template_id,
            "strategy_type": (c.strategy or {}).get("strategy_type"),
            "name": (gen.input or {}).get("product_name"),
            "headline": (c.copy or {}).get("headline"),
            "body": (c.copy or {}).get("body"),
            "cta": (c.copy or {}).get("cta"),
            "qa_passed": c.qa_passed,
            "quality_score": _avg_quality(c.qa_result),
            "created_at": gen.created_at.isoformat(timespec="seconds"),
        }
        try:
            (out_dir / entry["file"]).write_bytes(await download_bytes(c.s3_key))
            entry["status"] = "ok"
        except Exception as exc:
            entry["status"] = f"failed: {exc}"
            print(f"  최종본 다운로드 실패 {stem} — {exc}")
            entries.append(entry)
            continue
        if with_base:
            try:
                base_bytes = await download_bytes(candidate_base_key(gid, c.idx))
                base_file = f"{stem}_base.png"
                (out_dir / base_file).write_bytes(base_bytes)
                entry["base_file"] = base_file
            except Exception:
                entry["base_file"] = None  # 구버전 생성물엔 base가 없을 수 있음
        entries.append(entry)
        print(f"  받음 {stem} (base={'O' if entry.get('base_file') else 'X'})")
    return entries


async def main() -> None:
    parser = argparse.ArgumentParser(description="현행 파이프라인 생성 이미지 수집")
    parser.add_argument("--generation-id", nargs="*", default=[], help="특정 생성 ID들")
    parser.add_argument("--latest", type=int, default=0, help="최근 완료 생성 N건 자동 수집")
    parser.add_argument("--project-id", default=None, help="--latest 사용 시 프로젝트 필터")
    parser.add_argument(
        "--login-id", default=None, help="--latest 사용 시 내 계정(login_id) 생성분만"
    )
    parser.add_argument(
        "--product-contains", default=None, help="--latest 사용 시 상품명 부분일치 필터"
    )
    parser.add_argument("--no-base", action="store_true", help="base(텍스트 없는) 이미지 생략")
    parser.add_argument(
        "--out",
        default="scripts/measure/out/pipeline",
        help="출력 디렉터리 (backend 기준 상대경로)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as session:
        gens: list[AdGeneration] = []
        for gid in args.generation_id:
            gen = await session.get(AdGeneration, uuid.UUID(gid))
            if gen:
                gens.append(gen)
            else:
                print(f"생성 ID 없음 — {gid}")
        if args.latest:
            stmt = (
                select(AdGeneration)
                .where(AdGeneration.status == "completed")
                .order_by(AdGeneration.created_at.desc())
                .limit(args.latest)
            )
            if args.project_id:
                stmt = stmt.where(AdGeneration.project_id == uuid.UUID(args.project_id))
            if args.login_id:
                user_id = await session.scalar(
                    select(User.id).where(User.login_id == args.login_id)
                )
                if user_id is None:
                    print(f"login_id {args.login_id!r} 사용자를 찾을 수 없습니다")
                    return
                stmt = stmt.where(AdGeneration.created_by == user_id)
            if args.product_contains:
                stmt = stmt.where(
                    AdGeneration.input["product_name"].astext.ilike(f"%{args.product_contains}%")
                )
            gens.extend((await session.scalars(stmt)).all())
        if not gens:
            print("수집할 생성 건이 없습니다 — --latest N 또는 --generation-id를 지정하세요")
            return

        print(f"생성 {len(gens)}건 수집 시작 → {out_dir}")
        entries: list[dict] = []
        for gen in gens:
            print(f"[{str(gen.id)[:8]}] {(gen.input or {}).get('product_name', '?')}")
            entries.extend(await _fetch_generation(session, gen, out_dir, not args.no_base))

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "method": "pipeline",
        "items": entries,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for e in entries if e["status"] == "ok")
    print(f"\n완료 — 후보 {ok}/{len(entries)}장 수집, 결과 {out_dir}\\manifest.json")


if __name__ == "__main__":
    asyncio.run(main())
