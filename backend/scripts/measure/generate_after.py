# [측정-after] 현행 파이프라인(PIL 합성)으로 측정용 after 표본 생성 — 오타율/대비비 비교용
r"""before(baseline_text_in_image.py, AI가 카피까지 그림)의 짝이 되는 after 표본을 만든다.

현행 생성 파이프라인(generator_service.start_generation)을 in-process로 직접 호출한다.
uvicorn 서버는 필요 없다. 이미지 모델 분기(openai/gemini)는 시작 시 settings.generator_gen_mode를
읽으므로, 모드를 바꾸려면 GENERATOR_GEN_MODE(환경변수/.env)를 바꿔 재실행하면 된다.

변인통제 — before와 상품(baseline_text_in_image.SAMPLE_ADS 3종)을 완전히 동일화하고,
상품 이미지 없이 0부터 생성(순수 text-to-image 경로 일치)한다.

실행 (backend 디렉터리에서)
  :: gemini 모드(현재 .env 기본)
  uv run python scripts\measure\generate_after.py --n 2
  :: openai 모드로 전환 후 재실행
  set GENERATOR_GEN_MODE=openai
  uv run python scripts\measure\generate_after.py --n 2
  set GENERATOR_GEN_MODE=gemini

출력된 project_id를 fetch_generation_images.py --project-id 에 넘겨 수집한다.
"""

from __future__ import annotations

import argparse
import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from _bootstrap import setup

setup()

from baseline_text_in_image import SAMPLE_ADS, _slug  # noqa: E402  상품 정의·slug 규칙 재사용
from sqlalchemy import select  # noqa: E402

from core.config import settings  # noqa: E402
from core.db import AsyncSessionLocal  # noqa: E402
from core.models import Organization, Project  # noqa: E402
from domain.generator.service import generator_service  # noqa: E402
from domain.generator.service.generation_loop import (  # noqa: E402  루프 헬퍼 재사용
    _await_completion,
    _create_req,
)

# SAMPLE_ADS(name/headline/body/cta/scene)에는 타깃·목표가 없어 상품별로 고정 부여(변인통제).
_SEED_EXTRA: dict[str, tuple[str, str]] = {
    "스테인리스 텀블러": ("출퇴근길 커피를 챙기는 20~30대 직장인", "conversion"),
    "무선 이어폰": ("몰입과 이동이 잦은 20~30대", "conversion"),
    "멀티비타민": ("건강관리를 시작하는 30~40대 직장인", "conversion"),
}


def _seed(item: dict) -> dict:
    """SAMPLE_ADS 항목 → 생성 요청 seed(product_name/description/target/objective)."""
    target, objective = _SEED_EXTRA.get(item["name"], ("20~30대 소비자", "conversion"))
    return {
        "product_name": item["name"],
        "product_description": item["body"],
        "target_audience": target,
        "campaign_objective": objective,
    }


# 라벨(글자) 많은 신규 상품 3종 — 상품 이미지 업로드 시 라벨 텍스트 보존 실험용. 이미 seed 형식.
LABEL_PRODUCTS: list[dict] = [
    {
        "product_name": "오메가3",
        "product_description": "혈행 개선과 눈 건강을 돕는 고순도 rTG 오메가3, 하루 한 알",
        "target_audience": "건강관리에 관심 많은 40~50대",
        "campaign_objective": "conversion",
    },
    {
        "product_name": "수분크림",
        "product_description": "72시간 지속 보습, 히알루론산 수분크림으로 속당김 없는 하루",
        "target_audience": "건조함이 고민인 20~30대",
        "campaign_objective": "conversion",
    },
    {
        "product_name": "프로틴바",
        "product_description": "단백질 20g, 저당 프로틴바로 간편하게 챙기는 한 끼",
        "target_audience": "운동·다이어트하는 20~30대",
        "campaign_objective": "conversion",
    },
]


def _resolve_products(product_set: str) -> list[dict]:
    """product_set → 생성 대상 seed 리스트. sample=SAMPLE_ADS 매핑, label=LABEL_PRODUCTS."""
    if product_set == "label":
        return LABEL_PRODUCTS
    return [_seed(item) for item in SAMPLE_ADS]


def _image_model() -> str:
    """현재 모드의 이미지 모델명(배너용)."""
    if settings.generator_gen_mode == "gemini":
        return settings.generator_gemini_image_model
    return settings.generator_image_model


async def _resolve_project(project_id: str | None, tag: str) -> uuid.UUID:
    """측정 전용 프로젝트 확정 — 지정 시 존재 검증, 미지정 시 기존 조직 아래 신규 생성."""
    async with AsyncSessionLocal() as session:
        if project_id:
            pid = uuid.UUID(project_id)
            if await session.get(Project, pid) is None:
                raise SystemExit(f"project_id {project_id} 에 해당하는 프로젝트가 DB에 없음")
            return pid
        org = (await session.execute(select(Organization).limit(1))).scalar_one_or_none()
        if org is None:
            raise SystemExit(
                "조직이 하나도 없음 — 앱에서 조직/프로젝트를 먼저 만들고 --project-id로 지정하세요"
            )
        name = f"측정-after-{tag}-{datetime.now():%m%d-%H%M}"
        proj = Project(organization_id=org.id, name=name)
        session.add(proj)
        await session.commit()
        await session.refresh(proj)
        print(f"측정 전용 프로젝트 생성 — {name} ({proj.id})")
        return proj.id


async def main() -> None:
    parser = argparse.ArgumentParser(description="현행 파이프라인으로 측정용 after 표본 생성")
    parser.add_argument(
        "--n", type=int, default=2, help="상품당 생성 횟수 (1회=후보 3종, 기본 2 → 상품당 ≈6장)"
    )
    parser.add_argument(
        "--project-id", default=None, help="측정 전용 프로젝트 UUID (미지정 시 신규 생성)"
    )
    parser.add_argument("--tag", default=None, help="신규 프로젝트 이름 태그 (기본: 현재 gen_mode)")
    parser.add_argument(
        "--product-set",
        choices=["sample", "label"],
        default="sample",
        help="상품 세트 (sample=SAMPLE_ADS 3종, label=라벨 실험용 신규 3종)",
    )
    parser.add_argument(
        "--product-images",
        default=None,
        help="상품 이미지 폴더 — <상품slug>.png 를 업로드해 상품이미지 기반 생성",
    )
    args = parser.parse_args()

    if getattr(settings, "use_mock", False):
        print("⚠️  settings.use_mock=True — 목업 이미지일 수 있음. 실측이면 USE_MOCK=false 확인.")

    tag = args.tag or settings.generator_gen_mode
    products = _resolve_products(args.product_set)
    images_dir = Path(args.product_images) if args.product_images else None
    print(
        f"after 생성 — gen_mode={settings.generator_gen_mode} image_model={_image_model()} "
        f"상품 {len(products)}종({args.product_set}) × {args.n}회 "
        f"{'상품이미지 ' + str(images_dir) if images_dir else '상품이미지 없음(0부터 생성)'}"
    )
    pid = await _resolve_project(args.project_id, tag)

    gen_ids: list[str] = []
    for seed in products:
        name = seed["product_name"]
        print(f"[{name}]")
        temp_key: str | None = None
        if images_dir is not None:
            img_path = images_dir / f"{_slug(name)}.png"
            if not img_path.exists():
                raise SystemExit(f"상품 이미지 없음 — {img_path} (파일명은 상품 slug)")
            temp_key = await generator_service.store_temp_image(img_path.read_bytes())
            print(f"  상품 이미지 업로드 — {img_path.name} → {temp_key}")
        for rep in range(args.n):
            req = _create_req(seed, str(pid))
            if temp_key:
                req.product_image_temp_key = temp_key
            gid = await generator_service.start_generation(req)
            await _await_completion(gid)
            status = (generator_service._tasks.get(gid) or {}).get("status")
            detail = await generator_service.get_detail(gid)
            ncand = len(detail.get("candidates") or []) if detail else 0
            print(f"  생성 {rep + 1}/{args.n} — {gid} status={status} 후보 {ncand}")
            gen_ids.append(gid)
            await asyncio.sleep(0.5)  # 연속 호출 완화

    print(f"\n완료 — 생성 {len(gen_ids)}건, project_id={pid}")
    print(
        "다음 단계 — uv run python scripts\\measure\\fetch_generation_images.py "
        f"--project-id {pid} --out scripts\\measure\\out\\after_{tag}"
    )


if __name__ == "__main__":
    asyncio.run(main())
