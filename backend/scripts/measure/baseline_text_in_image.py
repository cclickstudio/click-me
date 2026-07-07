# [측정-before] 이미지 모델이 한글 카피까지 직접 그리게 하는 구방식 재현 — 오타율 비교의 대조군 생성
r"""PIL 텍스트 합성 전환(2026-06-21) 이전 방식을 재현한다.

현행 파이프라인은 텍스트를 PIL로 합성하지만, 초기에는 이미지 모델이 카피까지 그렸고
한글 오탈자·깨짐·잘림이 빈발했다. 이 스크립트는 그 방식으로 N장을 생성해
measure_text_accuracy.py의 대조군(before)을 만든다.

실행 (backend 디렉터리에서)
  uv run python scripts\measure\baseline_text_in_image.py --n 5
  uv run python scripts\measure\baseline_text_in_image.py --provider google_genai --n 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

from _bootstrap import setup

setup()

from core.config import settings  # noqa: E402
from domain.generator.contracts.enums import AdSize  # noqa: E402
from domain.generator.pipeline import image_providers  # noqa: E402

# 대조군용 샘플 광고 3종 — 현행 파이프라인에서도 같은 상품으로 생성해 비교한다.
SAMPLE_ADS: list[dict] = [
    {
        "name": "스테인리스 텀블러",
        "headline": "온도를 지키는 24시간",
        "body": "출근길 커피가 퇴근까지 따뜻하게, 이중 진공 스테인리스 텀블러",
        "cta": "지금 구매하기",
        "scene": "a sleek stainless steel tumbler on a wooden desk beside a laptop, "
        "soft morning light, minimal product photography",
    },
    {
        "name": "무선 이어폰",
        "headline": "소음은 끄고 몰입은 켜다",
        "body": "액티브 노이즈캔슬링과 30시간 배터리, 하루 종일 나만의 공간",
        "cta": "체험 예약하기",
        "scene": "modern wireless earbuds floating with charging case, dark gradient "
        "background with neon accent lighting, premium tech advertisement",
    },
    {
        "name": "멀티비타민",
        "headline": "하루 한 알의 균형",
        "body": "바쁜 일상에 필요한 12가지 영양소를 한 번에 챙기세요",
        "cta": "정기구독 시작",
        "scene": "vitamin bottle with fresh fruits and green leaves on bright clean "
        "kitchen counter, healthy lifestyle advertisement photography",
    },
]

_SIZE_MAP = {"square": AdSize.SQUARE, "landscape": AdSize.LANDSCAPE, "portrait": AdSize.PORTRAIT}


def _build_prompt(item: dict) -> str:
    """구방식 프롬프트 — 이미지 모델에게 한글 텍스트 렌더까지 요구한다."""
    return (
        "Create a professional Korean social media advertisement image.\n"
        f"Scene: {item['scene']}\n"
        "Render the following Korean text EXACTLY as given, directly inside the image:\n"
        f'- Headline (large, prominent): "{item["headline"]}"\n'
        f'- Body text (smaller): "{item["body"]}"\n'
        f'- CTA button with text: "{item["cta"]}"\n'
        "All Korean text must be clearly legible and spelled exactly as provided."
    )


def _slug(name: str) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "_", name).strip("_")


async def _generate_one(
    item: dict, rep: int, out_dir: Path, provider: str, model: str, size: AdSize, quality: str
) -> dict:
    fname = f"{_slug(item['name'])}_{rep:02d}.png"
    entry = {
        "file": fname,
        "method": "ai_text",
        "provider": provider,
        "model": model,
        "name": item["name"],
        "headline": item["headline"],
        "body": item["body"],
        "cta": item["cta"],
    }
    try:
        image_bytes = await image_providers.generate(
            _build_prompt(item), size, provider=provider, model=model, quality=quality
        )
        (out_dir / fname).write_bytes(image_bytes)
        entry["status"] = "ok"
        print(f"  생성됨 {fname}")
    except Exception as exc:  # 실패율 자체도 데이터 — 기록하고 계속
        entry["status"] = f"failed: {exc}"
        print(f"  실패 {fname} — {exc}")
    return entry


async def main() -> None:
    parser = argparse.ArgumentParser(description="구방식(AI 텍스트 렌더) 대조군 이미지 생성")
    parser.add_argument("--n", type=int, default=5, help="광고 1종당 반복 생성 수 (기본 5)")
    parser.add_argument(
        "--provider", default="openai", choices=["openai", "google_genai"], help="이미지 provider"
    )
    parser.add_argument("--model", default=None, help="이미지 모델 (기본: provider별 settings 값)")
    parser.add_argument("--size", default="square", choices=list(_SIZE_MAP), help="광고 사이즈")
    parser.add_argument("--quality", default=None, help="openai 품질 (기본: settings 값)")
    parser.add_argument(
        "--manifest-in", default=None, help="샘플 대신 쓸 광고 정의 JSON (SAMPLE_ADS와 같은 형식)"
    )
    parser.add_argument(
        "--out",
        default="scripts/measure/out/baseline",
        help="출력 디렉터리 (backend 기준 상대경로)",
    )
    args = parser.parse_args()

    model = args.model or (
        settings.generator_image_model
        if args.provider == "openai"
        else settings.generator_gemini_image_model
    )
    quality = args.quality or settings.generator_image_quality
    ads = SAMPLE_ADS
    if args.manifest_in:
        ads = json.loads(Path(args.manifest_in).read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"구방식 대조군 생성 — provider={args.provider} model={model} "
        f"광고 {len(ads)}종 × {args.n}회"
    )
    entries: list[dict] = []
    for item in ads:
        print(f"[{item['name']}]")
        for rep in range(args.n):
            entries.append(
                await _generate_one(
                    item, rep, out_dir, args.provider, model, _SIZE_MAP[args.size], quality
                )
            )
            await asyncio.sleep(0.5)  # 연속 호출 완화

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "method": "ai_text",
        "items": entries,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    ok = sum(1 for e in entries if e["status"] == "ok")
    print(f"\n완료 — 성공 {ok}/{len(entries)}장, 결과 {out_dir}\\manifest.json")
    print(
        "다음 단계 — uv run python scripts\\measure\\measure_text_accuracy.py --dir " + str(out_dir)
    )


if __name__ == "__main__":
    asyncio.run(main())
