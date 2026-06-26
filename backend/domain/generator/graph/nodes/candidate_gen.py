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
from domain.generator.contracts.enums import AdSize, TemplateType
from domain.generator.contracts.pipeline_schemas import (
    AdCopy,
    ProductAnalysis,
    StrategyOutput,
    StrategyPlan,
)
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.nodes.explain import generate_explanations
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.carousel import render_carousel_slide
from domain.generator.pipeline.carousel_copy import generate_carousel_copy
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


async def _generate_carousel(
    config: RunnableConfig,
    *,
    generation_id: str,
    product_analysis: ProductAnalysis,
    plan: StrategyPlan,
    gen_size: AdSize,
    width: int,
    height: int,
    brand_color: str | None,
    tone: str | None,
    product_cutout_bytes: bytes | None,
    logo_image_bytes: bytes | None,
) -> dict:
    """캐러셀 — 공통 배경 1장 생성 후 슬라이드별 PIL 텍스트로 3장 구성."""
    emit_progress(config, "candidates", 45, "캐러셀 배경 생성 중...")
    bg_bytes = await generate_image(
        product_analysis=product_analysis,
        strategy=plan.strategy,
        template=TemplateType.A,
        size=gen_size,
        brand_color=brand_color,
        tone=tone,
        product_cutout_bytes=product_cutout_bytes,
        headline="",
        body="",
        cta="",
    )

    emit_progress(config, "candidates", 60, "캐러셀 카피 생성 중...")
    slides = (await generate_carousel_copy(product_analysis)).slides[:3]
    if not slides:
        raise RuntimeError("캐러셀 카피 생성 실패")
    total = len(slides)

    candidates: list[dict] = []
    qa_results: list[dict] = []
    for idx, slide in enumerate(slides):
        slide_img = render_carousel_slide(bg_bytes, slide, idx + 1, total, brand_color)
        if logo_image_bytes is not None:
            slide_img = composite_logo(slide_img, logo_image_bytes, TemplateType.A)

        s3_key = candidate_key(generation_id, idx)
        await upload_bytes(slide_img, s3_key, content_type="image/png")
        # 공통 배경을 슬라이드별 base로도 저장 → 슬라이드 리레이아웃 지원
        await upload_bytes(
            bg_bytes, candidate_base_key(generation_id, idx), content_type="image/png"
        )

        qa = check_quality(
            ad_copy=AdCopy(headline=slide.headline, body=slide.body, cta=slide.cta or "보기"),
            target=product_analysis.target_audience,
        )
        qa_results.append(qa.model_dump())
        candidates.append(
            {
                "candidate_id": str(uuid.uuid4()),
                "idx": idx,
                "strategy": {
                    "strategy_type": plan.strategy.value,
                    "strategy_description": slide.role,
                    "rationale": f"캐러셀 {idx + 1}/{total} — {slide.role}",
                },
                "template_id": TemplateType.A.value,
                "copy": {"headline": slide.headline, "body": slide.body, "cta": slide.cta or ""},
                "image_prompt": None,
                "s3_key": s3_key,
                "requested_size": f"{width}x{height}",
                "rationale": slide.role,
            }
        )
        emit_progress(
            config, "candidates", 60 + (idx + 1) * 12, f"캐러셀 슬라이드 {idx + 1}/{total}"
        )

    return {"candidates": candidates, "qa_results": qa_results}


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
    # Gemini 경로: 누끼 스킵 — 원본 이미지를 직접 Gemini에 넘겨 전체 광고를 한 번에 생성.
    # OpenAI 경로: gpt-image-1로 누끼 후 마스크 인페인팅.
    product_cutout_bytes: bytes | None = None
    if product_image_bytes is not None:
        if settings.generator_image_provider == "google_genai":
            product_cutout_bytes = product_image_bytes  # 원본 그대로 전달
        else:
            try:
                product_cutout_bytes = await remove_product_background(product_image_bytes)
            except Exception:
                logger.exception("상품 누끼 실패 — 상품 없이 일반 생성으로 진행")
                product_cutout_bytes = None

    # 캐러셀(카드뉴스) — 공통 배경 1장 + 슬라이드별 PIL 텍스트 (단일 흐름과 분기)
    if req.get("format") == "carousel":
        return await _generate_carousel(
            config,
            generation_id=generation_id,
            product_analysis=product_analysis,
            plan=plans[0],
            gen_size=gen_size,
            width=width,
            height=height,
            brand_color=brand_color,
            tone=tone,
            product_cutout_bytes=product_cutout_bytes,
            logo_image_bytes=logo_image_bytes,
        )

    # 카피 3개를 LLM 1회 호출로 일괄 생성 (pipeline 모드일 때만).
    # 이미지는 텍스트 없이 생성되고(카피는 이후 PIL 렌더) 카피 완성을 기다릴 필요가 없으므로,
    # 카피 배치를 task로 띄워 이미지 생성과 병렬 진행 → 카피 LLM 왕복을 임계 경로에서 제거한다.
    # multimodal + 상품 이미지 없는 경우는 generate_image_and_copy 내부에서 카피를 만든다.
    copy_task: asyncio.Task | None = None
    if not (multimodal and product_cutout_bytes is None):

        async def _generate_copies() -> list[AdCopy]:
            copies = await generate_copies_batch(
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
            # 카피를 idx로 직접 인덱싱·zip하므로 개수가 다르면 명확히 실패시킨다(strict zip 대체).
            if len(copies) != len(plans):
                raise RuntimeError(f"카피 생성 개수 불일치: {len(copies)} != {len(plans)}")
            return copies

        copy_task = asyncio.create_task(_generate_copies())

    async def build(idx: int, variant_id: str, plan: StrategyPlan) -> dict:
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
            # 1. 이미지부터 생성 — 텍스트 없이 만들고 카피는 이후 PIL로 렌더하므로 카피를 기다리지 않는다.
            #    (상품 이미지가 있으면 마스크 인페인팅으로 상품 보존하며 생성)
            image_bytes = await generate_image(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
                product_cutout_bytes=product_cutout_bytes,
            )
            # 2. 병렬로 진행된 카피 배치 결과를 이 시점에 수령 (이미 완료돼 있을 가능성이 높다)
            ad_copy = (await copy_task)[idx]

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
            strategy=plan.strategy,
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

    # 생성 이유 설명은 카피·전략·QA만 필요하고 렌더 이미지가 불필요하다.
    # → 이미지 생성과 병렬로 미리 계산해 explain 노드의 LLM 왕복을 임계 경로에서 제거한다.
    # 카피가 빌드보다 먼저 준비되는 pipeline 경로에서만 선계산(멀티모달은 explain 노드가 폴백 처리).
    async def _precompute_explanations() -> list[dict]:
        copies = await copy_task
        target = req.get("target_audience") or "기존 타겟"
        product_name = req.get("product_name") or "(개선모드)"
        rows = [
            {
                "template": plan.template,
                "strategy_description": plan.strategy_description,
                "rationale": plan.rationale,
                "headline": copy.headline,
                "qa_passed": check_quality(
                    ad_copy=copy, target=product_analysis.target_audience
                ).overall_passed,
            }
            for plan, copy in zip(plans, copies, strict=True)
        ]
        return await generate_explanations(product_name, target, rows)

    build_coros = [
        build(i, vid, plan) for i, (vid, plan) in enumerate(zip(_VARIANT_IDS, plans, strict=True))
    ]
    explanations: list[dict] | None = None
    if copy_task is not None:
        # 선계산을 별도 task로 띄우지 않고 같은 gather에 코루틴으로 넘겨 빌드와 동일하게 관리한다.
        *results, explanations = await asyncio.gather(*build_coros, _precompute_explanations())
    else:
        results = list(await asyncio.gather(*build_coros))

    candidates = sorted(results, key=lambda c: c["idx"])
    qa_results = [c.pop("_quality_report") for c in candidates]
    out: dict = {"candidates": candidates, "qa_results": qa_results}
    if explanations is not None:
        out["explanations"] = explanations
    return out
