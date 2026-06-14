import asyncio
import uuid
from datetime import UTC, datetime

import aioboto3
from langsmith import traceable

from core.config import settings
from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.schemas import (
    GeneratedAdVariant,
    GenerateRequest,
    GenerateResult,
    ImproveRequest,
    ProductAnalysis,
    StrategyOutput,
    StrategyPlan,
)
from domain.generator.pipeline.copy_generator import generate_copy
from domain.generator.pipeline.image_analyzer import analyze_image
from domain.generator.pipeline.image_generator import generate_image
from domain.generator.pipeline.product_analyzer import analyze_product
from domain.generator.pipeline.quality_checker import check_quality
from domain.generator.pipeline.strategy_planner import plan_strategies
from domain.generator.pipeline.template_selector import select_template
from domain.generator.pipeline.text_compositor import composite_text
from domain.generator.pipeline.text_inpainter import inpaint_text_zone


async def _upload_to_s3(image_bytes: bytes, s3_key: str) -> str:
    """이미지를 S3에 업로드하고 24시간 유효 presigned URL 반환."""
    session = aioboto3.Session(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    async with session.client("s3") as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket_name,
            Key=s3_key,
            Body=image_bytes,
            ContentType="image/png",
        )
        url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket_name, "Key": s3_key},
            ExpiresIn=86400,
        )
    return url


async def _build_variant(
    variant_id: str,
    generation_id: str,
    plan: StrategyPlan,
    strategy_output: StrategyOutput,
    product_analysis: ProductAnalysis,
    size,
    brand_color: str | None,
    tone: str | None,
) -> GeneratedAdVariant:
    # 1. 배경 이미지 생성
    bg_bytes = await generate_image(
        product_analysis=product_analysis,
        strategy=plan.strategy,
        template=plan.template,
        size=size,
        brand_color=brand_color,
        tone=tone,
    )

    # 2. 이미지 분석
    image_analysis = await analyze_image(bg_bytes)

    # 3. 이미지에 맞는 카피 생성
    ad_copy = await generate_copy(
        product_analysis=product_analysis,
        strategy_output=strategy_output,
        image_analysis=image_analysis,
        template=plan.template,
    )

    # 4. 인페인팅(텍스트 존 자연화) + 품질 검증 병렬 실행
    inpainted_bg, quality_report = await asyncio.gather(
        inpaint_text_zone(
            bg_bytes=bg_bytes,
            template=plan.template,
            image_analysis=image_analysis,
            brand_color=brand_color,
        ),
        check_quality(ad_copy=ad_copy, target=product_analysis.target_audience),
    )

    # 5. PIL로 한국어 텍스트 합성 (AI가 디자인한 배경 위에)
    image_bytes = await asyncio.to_thread(
        composite_text,
        inpainted_bg,
        ad_copy.headline,
        ad_copy.body,
        ad_copy.cta,
        plan.template,
        brand_color,
        image_analysis,
    )

    s3_key = f"generated/{generation_id}/{variant_id}.png"
    image_url = await _upload_to_s3(image_bytes, s3_key)

    return GeneratedAdVariant(
        variant_id=variant_id,
        strategy=plan.strategy,
        template=plan.template,
        image_s3_key=s3_key,
        image_url=image_url,
        headline=ad_copy.headline,
        body=ad_copy.body,
        cta=ad_copy.cta,
        rationale=plan.rationale,
        quality_report=quality_report,
    )


def _to_strategy_plans(strategy_outputs: list[StrategyOutput]) -> list[StrategyPlan]:
    return [
        StrategyPlan(
            strategy=s.strategy,
            strategy_description=s.strategy_description,
            template=select_template(s.strategy),
            rationale=s.rationale,
        )
        for s in strategy_outputs
    ]


@traceable(name="GeneratorService.generate", metadata={"pipeline": "generator", "mode": "create"})
async def generate_ad(request: GenerateRequest) -> GenerateResult:
    generation_id = str(uuid.uuid4())

    product_analysis = await analyze_product(
        product_name=request.product_name,
        description=request.description,
        target=request.target,
        objective=request.objective,
    )

    strategy_outputs = await plan_strategies(product_analysis)
    plans = _to_strategy_plans(strategy_outputs)

    variant_ids = ["A", "B", "C"]
    variants = await asyncio.gather(
        *[
            _build_variant(
                variant_id=vid,
                generation_id=generation_id,
                plan=plan,
                strategy_output=so,
                product_analysis=product_analysis,
                size=request.size,
                brand_color=request.brand_color,
                tone=request.tone,
            )
            for vid, plan, so in zip(
                variant_ids[: len(plans)], plans, strategy_outputs, strict=False
            )
        ]
    )

    return GenerateResult(
        generation_id=generation_id,
        mode=GenerationMode.CREATE,
        variants=list(variants),
        created_at=datetime.now(UTC).isoformat(),
    )


@traceable(name="GeneratorService.improve", metadata={"pipeline": "generator", "mode": "improve"})
async def improve_ad(request: ImproveRequest) -> GenerateResult:
    generation_id = str(uuid.uuid4())

    improvement_context = (
        f"기존 광고 S3 키: {request.existing_ad_s3_key}\n"
        f"시뮬레이션 피드백: {request.simulation_summary}"
    )
    if request.fix_requests:
        improvement_context += f"\n추가 수정 요청: {request.fix_requests}"

    # 개선모드: 시뮬레이션 피드백 기반 전략 수립
    # product_name은 이미지 프롬프트 품질을 위해 전달받고, 없으면 S3 키를 대신 사용
    effective_product_name = request.product_name or request.existing_ad_s3_key
    improve_analysis = ProductAnalysis(
        product_name=effective_product_name,
        core_values=[],
        pain_points=[],
        benefits=[],
        target_audience="기존 타겟",
        objective="광고 개선",
    )

    strategy_outputs = await plan_strategies(
        product_analysis=improve_analysis,
        improvement_context=improvement_context,
    )
    plans = _to_strategy_plans(strategy_outputs)

    variant_ids = ["A", "B", "C"]
    variants = await asyncio.gather(
        *[
            _build_variant(
                variant_id=vid,
                generation_id=generation_id,
                plan=plan,
                strategy_output=so,
                product_analysis=improve_analysis,
                size=request.size,
                brand_color=request.brand_color,
                tone=request.tone,
            )
            for vid, plan, so in zip(
                variant_ids[: len(plans)], plans, strategy_outputs, strict=False
            )
        ]
    )

    return GenerateResult(
        generation_id=generation_id,
        mode=GenerationMode.IMPROVE,
        variants=list(variants),
        created_at=datetime.now(UTC).isoformat(),
    )
