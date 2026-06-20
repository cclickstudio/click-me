"""노드 4 — 광고 후보 3종 생성.

생성 방식(GENERATOR_GEN_MODE)에 따라 변종마다 둘 중 하나로 동작한다.
- pipeline: 카피 생성 → 제품 이미지 생성(단계 분리) → 품질검증 → S3 업로드.
- multimodal: 한 모델 호출로 카피+이미지 동시 생성 → 품질검증 → S3 업로드.
품질검증(QualityReport)은 이 노드에서 qa_results로 함께 산출한다(별도 run_qa 노드 없음).
"""

from __future__ import annotations

import asyncio
import logging
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
from domain.generator.pipeline.image_generator import composite_logo, generate_image
from domain.generator.pipeline.multimodal_generator import generate_image_and_copy
from domain.generator.pipeline.quality_checker import check_quality
from tools.storage.s3 import candidate_key, download_bytes, upload_bytes

logger = logging.getLogger("clickme")

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

    logo_s3_key = req.get("brand_logo_s3_key")
    logo_image_bytes: bytes | None = None
    if logo_s3_key:
        try:
            logo_image_bytes = await download_bytes(logo_s3_key)
        except Exception:
            logo_image_bytes = None

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

            # 2. 이미지 생성 (카피 텍스트를 프롬프트에 반영)
            image_bytes = await generate_image(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
                headline=ad_copy.headline,
                body=ad_copy.body,
                cta=ad_copy.cta,
            )

        # 3. 품질검증 (순수 동기 함수)
        quality_report = check_quality(ad_copy=ad_copy, target=product_analysis.target_audience)

        # 3. 로고 합성 (brand_logo_s3_key 제공 시)
        if logo_image_bytes is not None:
            image_bytes = composite_logo(image_bytes, logo_image_bytes, plan.template)

        # 4. S3 업로드
        s3_key = candidate_key(generation_id, idx)
        try:
            await upload_bytes(image_bytes, s3_key, content_type="image/png")
            logger.info("S3 업로드 완료: key=%s", s3_key)
        except Exception:
            logger.exception("S3 업로드 실패: key=%s", s3_key)
            raise

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
            for i, (vid, plan) in enumerate(zip(_VARIANT_IDS, plans, strict=True))
        ]
    )
    candidates = sorted(results, key=lambda c: c["idx"])
    qa_results = [c.pop("_quality_report") for c in candidates]
    return {"candidates": candidates, "qa_results": qa_results}
