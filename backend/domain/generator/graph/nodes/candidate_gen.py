"""노드 4 — 광고 후보 3종 생성.

생성 방식(GENERATOR_GEN_MODE)에 따라 변종마다 둘 중 하나로 동작한다.
- pipeline: 카피 생성 → 제품 이미지 생성(단계 분리) → 품질검증 → S3 업로드.
- multimodal: 한 모델 호출로 카피+이미지 동시 생성 → 품질검증 → S3 업로드.
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
from domain.generator.pipeline.image_generator import generate_image
from domain.generator.pipeline.multimodal_generator import generate_image_and_copy
from domain.generator.pipeline.quality_checker import check_quality
from tools.storage.s3 import candidate_key, upload_bytes

_VARIANT_IDS = ["A", "B", "C"]


def _map_ad_size(width: int, height: int) -> AdSize:
    """목표 치수를 gpt-image-2 생성 사이즈(AdSize)로 매핑."""
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

    done = 0
    multimodal = settings.generator_gen_mode == "multimodal"

    async def build(idx: int, variant_id: str, plan: StrategyPlan) -> dict:
        nonlocal done

        if multimodal:
            # 1+2. 한 모델 호출로 카피·이미지 동시 생성 (스타일 일관성), 이후 품질검증
            image_bytes, ad_copy = await generate_image_and_copy(
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
        else:
            # 1. 카피 먼저 생성 (이미지 생성 전 텍스트 확정)
            ad_copy = await generate_copy(
                product_analysis=product_analysis,
                strategy_output=StrategyOutput(
                    strategy=plan.strategy,
                    strategy_description=plan.strategy_description,
                    rationale=plan.rationale,
                ),
                template=plan.template,
            )

            # 2. 이미지 생성 + 품질검증 병렬 (단계 분리)
            image_bytes, quality_report = await asyncio.gather(
                generate_image(
                    product_analysis=product_analysis,
                    strategy=plan.strategy,
                    template=plan.template,
                    size=gen_size,
                    brand_color=brand_color,
                    tone=tone,
                ),
                check_quality(ad_copy=ad_copy, target=product_analysis.target_audience),
            )

        # 3. S3 업로드
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
