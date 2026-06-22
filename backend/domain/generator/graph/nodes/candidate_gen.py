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
from domain.generator.pipeline.copy_generator import generate_copies_batch
from domain.generator.pipeline.image_generator import (
    composite_logo,
    generate_image,
    remove_product_background,
)
from domain.generator.pipeline.multimodal_generator import generate_image_and_copy
from domain.generator.pipeline.quality_checker import check_quality
from domain.generator.pipeline.text_overlay import render_ad_text
from tools.storage.s3 import candidate_base_key, candidate_key, download_bytes, upload_bytes

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
    product_image_bytes: bytes | None = state.get("product_image_bytes")

    logo_s3_key = req.get("brand_logo_s3_key")
    logo_image_bytes: bytes | None = None
    if logo_s3_key:
        try:
            logo_image_bytes = await download_bytes(logo_s3_key)
        except Exception:
            logo_image_bytes = None

    done = 0
    multimodal = settings.generator_gen_mode == "multimodal"

    # 상품 이미지 누끼는 후보 3종 공통 → gather 전 1회만 실행 (API 호출 절약).
    # 상품 이미지가 있으면 모드와 무관하게 컴포즈(마스크 인페인팅) 경로를 탄다.
    product_cutout_bytes: bytes | None = None
    if product_image_bytes is not None:
        try:
            product_cutout_bytes = await remove_product_background(product_image_bytes)
        except Exception:
            logger.exception("상품 누끼 실패 — 상품 없이 일반 생성으로 진행")
            product_cutout_bytes = None

    # 카피 3개를 LLM 1회 호출로 일괄 생성 (pipeline 모드일 때만).
    # multimodal + 상품 이미지 없는 경우는 generate_image_and_copy 내부에서 카피를 만든다.
    batch_copies = [None, None, None]
    if not (multimodal and product_cutout_bytes is None):
        batch_copies = await generate_copies_batch(
            product_analysis=product_analysis,
            strategy_outputs=[
                (
                    StrategyOutput(
                        strategy=plan.strategy,
                        strategy_description=plan.strategy_description,
                        rationale=plan.rationale,
                    ),
                    plan.template,
                )
                for plan in plans
            ],
            improvement_context=req.get("improvement_context"),
        )

    async def build(idx: int, variant_id: str, plan: StrategyPlan, ad_copy) -> dict:
        nonlocal done

        # multimodal 한방 생성은 상품 픽셀 보존이 불가하므로, 상품 이미지가 있으면 사용하지 않는다.
        if multimodal and product_cutout_bytes is None:
            # 1+2. 한 모델 호출로 카피·이미지 동시 생성 (스타일 일관성)
            image_bytes, ad_copy = await generate_image_and_copy(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
            )
        else:
            # 1. 카피는 이미 배치 생성됨 — 이미지만 생성
            # 2. 이미지 생성 — 상품 이미지가 있으면 마스크 인페인팅으로 상품 보존하며 생성
            image_bytes = await generate_image(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
                product_cutout_bytes=product_cutout_bytes,
                headline=ad_copy.headline,
                body=ad_copy.body,
                cta=ad_copy.cta,
            )

        # 3. 텍스트 없는 base 이미지를 별도 저장 — 플랫폼별 리레이아웃 렌더의 원본
        base_key = candidate_base_key(generation_id, idx)
        try:
            await upload_bytes(image_bytes, base_key, content_type="image/png")
        except Exception:
            logger.exception("base 이미지 업로드 실패: key=%s", base_key)

        # 4. 카피 텍스트를 PIL로 렌더 (AI는 텍스트 미생성 — 잘림·오탈자 방지)
        image_bytes = render_ad_text(
            image_bytes,
            headline=ad_copy.headline,
            body=ad_copy.body,
            cta=ad_copy.cta,
            template=plan.template,
            brand_color=brand_color,
        )

        # 5. 품질검증 (순수 동기 함수)
        quality_report = check_quality(ad_copy=ad_copy, target=product_analysis.target_audience)

        # 6. 로고 합성 (brand_logo_s3_key 제공 시)
        if logo_image_bytes is not None:
            image_bytes = composite_logo(image_bytes, logo_image_bytes, plan.template)

        # 7. S3 업로드
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
            build(i, vid, plan, copy)
            for i, (vid, plan, copy) in enumerate(
                zip(_VARIANT_IDS, plans, batch_copies, strict=True)
            )
        ]
    )
    candidates = sorted(results, key=lambda c: c["idx"])
    qa_results = [c.pop("_quality_report") for c in candidates]
    return {"candidates": candidates, "qa_results": qa_results}
