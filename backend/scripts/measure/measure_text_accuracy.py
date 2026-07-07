# [측정-오타율] VLM(gpt-4o)으로 광고 이미지 속 한글 텍스트의 오탈자·깨짐·잘림을 판정해 오타율 집계
r"""이미지 디렉터리(manifest.json 포함)를 받아 텍스트 렌더 품질을 판정한다.

- manifest에 기대 카피(headline/body/cta)가 있으면 기대값 대비 판정
  (exact | typo | broken | cut | missing)
- 기대 카피가 없으면 독립 모드 — 이미지 안 텍스트 결함 유무만 판정
- 결과: text_accuracy.csv + 요약(방식별 무결점 비율·요소별 정확율)

실행 (backend 디렉터리에서)
  uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\baseline
  uv run python scripts\measure\measure_text_accuracy.py --dir scripts\measure\out\pipeline
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

from _bootstrap import setup

setup()

from openai import AsyncOpenAI  # noqa: E402

from core.config import settings  # noqa: E402

_STATUSES = ["exact", "typo", "broken", "cut", "missing"]
_STATUS_KO = {
    "exact": "정확",
    "typo": "오탈자",
    "broken": "글자깨짐",
    "cut": "잘림",
    "missing": "누락",
}

_JUDGE_SYSTEM = (
    "너는 광고 이미지의 텍스트 렌더 품질 검수자다. 이미지에 보이는 텍스트를 있는 그대로 "
    "읽고, 기대 텍스트와 글자 단위로 대조해 JSON으로만 답한다. 판정 기준 — "
    "exact: 기대 텍스트와 완전 일치 / typo: 글자가 다르거나 빠짐(오탈자) / "
    "broken: 획이 뭉개지거나 존재하지 않는 글자 형태(깨짐) / cut: 텍스트가 이미지 경계나 "
    "다른 요소에 물리적으로 잘림 / missing: 해당 텍스트가 이미지에 없음. "
    "의심스러우면 exact가 아닌 쪽으로 판정한다."
)


def _judge_prompt(entry: dict) -> str:
    if entry.get("headline"):
        return (
            "이 광고 이미지에 보이는 텍스트를 빠짐없이 검사하라.\n"
            "1) 아래 기대 카피 각각을 찾아 판정한다.\n"
            f'- headline: "{entry["headline"]}"\n'
            f'- body: "{entry["body"]}"\n'
            f'- cta: "{entry["cta"]}"\n'
            "2) 그 외 이미지에 보이는 모든 텍스트(상품 라벨·로고·배경 문구·의미 없는 문자 등)를 "
            "각각 하나의 항목으로 열거해 판정한다. 정상 렌더된 텍스트도 status exact로 포함한다.\n"
            "다음 JSON 형식으로만 답하라.\n"
            '{"elements": {"headline": {"status": "exact|typo|broken|cut|missing",'
            ' "seen": "실제로 보이는 텍스트"}, "body": {...}, "cta": {...}},'
            ' "other_texts": [{"seen": "보이는 텍스트", "status": "exact|typo|broken|cut"}]}'
        )
    return (
        "이 광고 이미지 안의 모든 텍스트를 검사하라. 한글 오탈자·깨진 글자·잘린 텍스트·"
        "의미 없는 문자열이 있는지 판정해 다음 JSON 형식으로만 답하라.\n"
        '{"has_text_defect": true|false, "defects": ["발견한 결함 서술"],'
        ' "seen_texts": ["보이는 텍스트"]}'
    )


async def _judge_one(client: AsyncOpenAI, model: str, img_dir: Path, entry: dict) -> list[dict]:
    b64 = base64.b64encode((img_dir / entry["file"]).read_bytes()).decode()
    response = await client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _JUDGE_SYSTEM},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _judge_prompt(entry)},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"},
                    },
                ],
            },
        ],
    )
    verdict = json.loads(response.choices[0].message.content or "{}")
    rows: list[dict] = []
    common = {"file": entry["file"], "method": entry.get("method", "?")}
    if entry.get("headline"):
        for element in ("headline", "body", "cta"):
            v = (verdict.get("elements") or {}).get(element) or {}
            status = v.get("status") if v.get("status") in _STATUSES else "missing"
            rows.append(
                {
                    **common,
                    "element": element,
                    "status": status,
                    "expected": entry.get(element) or "",
                    "seen": v.get("seen") or "",
                }
            )
        # 이미지 내 기대 카피 외 모든 텍스트 — 정상·결함 모두 인스턴스로 수집(오타율 분모에 포함).
        for other in verdict.get("other_texts") or []:
            status = other.get("status") if other.get("status") in _STATUSES else "broken"
            rows.append(
                {
                    **common,
                    "element": "other",
                    "status": status,
                    "expected": "",
                    "seen": other.get("seen") or "",
                }
            )
    else:
        defects = verdict.get("defects") or []
        if verdict.get("has_text_defect") and defects:
            rows.extend(
                {**common, "element": "any", "status": "broken", "expected": "", "seen": d}
                for d in defects
            )
        else:
            rows.append({**common, "element": "any", "status": "exact", "expected": "", "seen": ""})
    return rows


def _summarize(rows: list[dict]) -> None:
    by_method: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_method[r["method"]].append(r)
    for method, rs in by_method.items():
        files = {r["file"] for r in rs}
        defect_files = {r["file"] for r in rs if r["status"] != "exact"}
        print(f"\n[{method}] 이미지 {len(files)}장")
        clean_pct = (len(files) - len(defect_files)) / len(files) * 100
        print(f"  무결점 이미지 비율  {clean_pct:.1f}%  (결함 {len(defect_files)}장)")
        # 전체 결함율 — 카피 3칸 + 기타(상품 라벨·배경 등) 이미지 내 모든 텍스트 인스턴스 기준.
        defect_inst = sum(1 for r in rs if r["status"] != "exact")
        print(
            f"  전체 결함율        {defect_inst / len(rs) * 100:.1f}%  "
            f"({defect_inst}/{len(rs)} 텍스트, 이미지 내 모든 글자 기준)"
        )
        for element, label in (
            ("headline", "headline"),
            ("body", "body"),
            ("cta", "cta"),
            ("other", "기타"),
            ("any", "any"),
        ):
            ers = [r for r in rs if r["element"] == element]
            if not ers:
                continue
            exact = sum(1 for r in ers if r["status"] == "exact")
            dist = Counter(_STATUS_KO[r["status"]] for r in ers if r["status"] != "exact")
            dist_s = ", ".join(f"{k} {v}" for k, v in dist.most_common()) or "-"
            pct = exact / len(ers) * 100
            print(f"  {label:8s} 정확 {exact}/{len(ers)} ({pct:.0f}%)  결함: {dist_s}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="광고 이미지 텍스트 오타율 측정 (VLM 판정)")
    parser.add_argument("--dir", required=True, help="이미지+manifest.json 디렉터리")
    parser.add_argument("--model", default="gpt-4o", help="판정 VLM (기본 gpt-4o)")
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N장만 판정 (0=전체)")
    parser.add_argument("--out", default=None, help="CSV 경로 (기본 <dir>/text_accuracy.csv)")
    args = parser.parse_args()

    img_dir = Path(args.dir)
    manifest = json.loads((img_dir / "manifest.json").read_text(encoding="utf-8"))
    entries = [e for e in manifest["items"] if e.get("status") == "ok" or "status" not in e]
    if args.limit:
        entries = entries[: args.limit]
    print(f"판정 대상 {len(entries)}장 (model={args.model})")

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    sem = asyncio.Semaphore(args.concurrency)
    rows: list[dict] = []

    async def _run(entry: dict) -> None:
        async with sem:
            try:
                result = await _judge_one(client, args.model, img_dir, entry)
                rows.extend(result)
                bad = [r for r in result if r["status"] != "exact"]
                mark = (
                    "결함 " + ", ".join(_STATUS_KO[r["status"]] for r in bad) if bad else "무결점"
                )
                print(f"  {entry['file']} — {mark}")
            except Exception as exc:
                print(f"  {entry['file']} — 판정 실패: {exc}")

    await asyncio.gather(*[_run(e) for e in entries])

    out_path = Path(args.out) if args.out else img_dir / "text_accuracy.csv"
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f, fieldnames=["file", "method", "element", "status", "expected", "seen"]
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["file"], r["element"])))
    _summarize(rows)
    print(f"\nCSV 저장 — {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
