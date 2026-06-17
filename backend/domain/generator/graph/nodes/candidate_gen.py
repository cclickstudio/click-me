"""노드 4 — 광고 후보 3종 생성 (yunseop 렌더링 체인).

변종마다: 배경 생성 → 이미지 분석 → 카피 → (인페인팅 ∥ 품질검증)
→ 목표 치수 보정 → 한글 텍스트·로고 합성 → S3 업로드.
품질검증(QualityReport)은 이 노드에서 qa_results로 함께 산출한다(별도 run_qa 노드 없음).
"""

from __future__ import annotations

import asyncio
import uuid

from langchain_core.runnables import RunnableConfig

from core.config import settings
from domain.generator.contracts.enums import AdSize
from domain.generator.contracts.pipeline_schemas import (
    ProductAnalysis,
    StrategyOutput,
    StrategyPlan,
)
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.copy_generator import generate_copy
from domain.generator.pipeline.image_analyzer import analyze_image
from domain.generator.pipeline.image_generator import generate_image
from domain.generator.pipeline.multimodal_generator import generate_image_and_copy
from domain.generator.pipeline.quality_checker import check_quality
from domain.generator.pipeline.text_compositor import composite_text, resize_to_target
from domain.generator.pipeline.text_inpainter import inpaint_text_zone
from tools.storage.s3 import candidate_key, download_bytes, upload_bytes

_VARIANT_IDS = ["A", "B", "C"]


def _map_ad_size(width: int, height: int) -> AdSize:
    """목표 치수를 gpt-image-1 생성 사이즈(AdSize)로 매핑."""
    if width == height:
        return AdSize.SQUARE
    return AdSize.LANDSCAPE if width > height else AdSize.PORTRAIT


async def generate_candidates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "candidates", 40, "광고 후보 생성 중 (0/3)")
    req = state["request"]
    generation_id = state["generation_id"]
    product_analysis = ProductAnalysis(**state["product_analysis"])
    plans = [StrategyPlan(**p) for p in state["plans"]]

    width, height = req["width"], req["height"]
    gen_size = _map_ad_size(width, height)
    brand_color = req.get("brand_color")
    tone = req.get("tone_and_manner")

    # 로고: S3 키가 있으면 1회만 다운로드
    logo_png: bytes | None = None
    if req.get("brand_logo_s3_key"):
        try:
            logo_png = await download_bytes(req["brand_logo_s3_key"])
        except Exception:
            logo_png = None

    done = 0

    async def build(idx: int, variant_id: str, plan: StrategyPlan) -> dict:
        nonlocal done

        if settings.generator_gen_mode == "multimodal":
            # 멀티모달: 한 모델이 카피가 렌더링된 완성형 이미지 + 카피를 한 번에 생성
            # (배경생성·이미지분석·카피·인페인팅·합성 단계를 대체)
            creative, ad_copy = await generate_image_and_copy(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
            )
            quality_report = await check_quality(
                ad_copy=ad_copy, target=product_analysis.target_audience
            )
            image_bytes = resize_to_target(creative, width, height)
        else:
            # pipeline: 텍스트 없는 배경 → 분석 → 카피 → 인페인팅 → 한글 텍스트·로고 합성
            # 1. 배경 이미지 (텍스트 없음)
            bg_bytes = await generate_image(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
            )

            # 2. 이미지 분석
            image_analysis = await analyze_image(bg_bytes)

            # 3. 이미지에 맞는 카피
            ad_copy = await generate_copy(
                product_analysis=product_analysis,
                strategy_output=StrategyOutput(
                    strategy=plan.strategy,
                    strategy_description=plan.strategy_description,
                    rationale=plan.rationale,
                ),
                image_analysis=image_analysis,
                template=plan.template,
            )

            # 4. 인페인팅(텍스트존 자연화) + 품질검증 병렬
            inpainted_bg, quality_report = await asyncio.gather(
                inpaint_text_zone(
                    bg_bytes=bg_bytes,
                    template=plan.template,
                    image_analysis=image_analysis,
                    brand_color=brand_color,
                ),
                check_quality(ad_copy=ad_copy, target=product_analysis.target_audience),
            )

            # 5. 목표 치수 보정(배경) 후 최종 치수에서 한글 텍스트·로고 합성
            inpainted_bg = resize_to_target(inpainted_bg, width, height)
            image_bytes = await asyncio.to_thread(
                composite_text,
                inpainted_bg,
                ad_copy.headline,
                ad_copy.body,
                ad_copy.cta,
                plan.template,
                brand_color,
                image_analysis,
                logo_png,
            )

        # 6. S3 업로드
        s3_key = candidate_key(generation_id, idx)
        await upload_bytes(image_bytes, s3_key, content_type="image/png")

        done += 1
        emit_progress(config, "candidates", 40 + done * 12, f"광고 후보 생성 중 ({done}/3)")

        return {
            "candidate_id": str(uuid.uuid4()),
            "idx": idx,
            "strategy": {
                "strategy_type": plan.strategy.value,
                "strategy_description": plan.strategy_description,
                "rationale": plan.rationale,
            },
            "template_id": plan.template.value,
            "copy": ad_copy.model_dump(),
            "image_prompt": None,
            "s3_key": s3_key,
            "requested_size": f"{width}x{height}",
            "rationale": plan.rationale,
            "_quality_report": quality_report.model_dump(),
        }

    results = await asyncio.gather(
        *[
            build(i, vid, plan)
            for i, (vid, plan) in enumerate(zip(_VARIANT_IDS, plans, strict=False))
        ]
    )
    candidates = sorted(results, key=lambda c: c["idx"])
    qa_results = [c.pop("_quality_report") for c in candidates]
    return {"candidates": candidates, "qa_results": qa_results}
