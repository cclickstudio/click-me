"""노드 4 — 광고 후보 3종 생성.

생성 방식(GENERATOR_GEN_MODE)에 따라 변종마다 둘 중 하나로 동작한다.
- openai: 카피 생성 → 이미지 생성(상품있음 인페인팅 / 없음 0부터, 단계 분리) → 품질검증 → S3.
- gemini: 한 Gemini 호출로 카피+이미지 동시 생성(상품있음 멀티모달 입력) → 품질검증 → S3.
품질검증(QualityReport)은 이 노드에서 qa_results로 함께 산출한다(별도 run_qa 노드 없음).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from langchain_core.runnables import RunnableConfig

from core.config import settings
from domain.generator.contracts.enums import AdSize, GenerationMode, TemplateType
from domain.generator.contracts.pipeline_schemas import (
    AdCopy,
    ProductAnalysis,
    StrategyOutput,
    StrategyPlan,
)
from domain.generator.contracts.schemas import CandidateExplanation
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.nodes.explain import generate_explanations
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.carousel import render_carousel_slide
from domain.generator.pipeline.carousel_copy import generate_carousel_copy
from domain.generator.pipeline.copy_generator import generate_copies_batch, generate_copy
from domain.generator.pipeline.image_generator import (
    composite_logo,
    generate_image,
    remove_product_background,
)
from domain.generator.pipeline.multimodal_generator import generate_image_and_copy
from domain.generator.pipeline.quality_checker import check_quality
from domain.generator.pipeline.text_overlay import render_ad_text
from tools.storage.s3 import (
    candidate_base_key,
    candidate_key,
    download_bytes,
    product_cutout_key,
    upload_bytes,
)

logger = logging.getLogger("clickme")

_VARIANT_IDS = ["A", "B", "C"]


def _map_ad_size(width: int, height: int) -> AdSize:
    """목표 치수를 이미지 모델 생성 사이즈(AdSize)로 매핑."""
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
    product_image_bytes: bytes | None,
    logo_image_bytes: bytes | None,
    gemini: bool,
    improvement_context: str | None = None,
) -> dict:
    """캐러셀 — 공통 배경 1장 생성 후 슬라이드별 PIL 텍스트로 3장 구성."""
    emit_progress(config, "candidates", 45, "캐러셀 배경 생성 중...")
    if gemini:
        # gemini 모드 — Gemini로 배경 생성. 카피는 슬라이드별로 따로 만들므로 함께 나온 카피는 버린다.
        bg_bytes, _ = await generate_image_and_copy(
            product_analysis=product_analysis,
            strategy=plan.strategy,
            template=TemplateType.A,
            size=gen_size,
            brand_color=brand_color,
            tone=tone,
            improvement_context=improvement_context,
            product_image_bytes=product_image_bytes,
        )
    else:
        bg_bytes = await generate_image(
            product_analysis=product_analysis,
            strategy=plan.strategy,
            template=TemplateType.A,
            size=gen_size,
            brand_color=brand_color,
            tone=tone,
            product_cutout_bytes=product_cutout_bytes,
            improvement_context=improvement_context,
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
            product_name=product_analysis.product_name,
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
    req = state["request"]

    # 개선 모드는 단일 후보 전용 경로로 분기
    if req.get("mode") == GenerationMode.IMPROVE:
        return await _generate_improve_candidate(state, config)

    emit_progress(config, "candidates", 40, "광고 후보 생성 중 (0/3)")
    generation_id = state["generation_id"]
    product_analysis = ProductAnalysis(**state["product_analysis"])
    plans = [StrategyPlan(**p) for p in state["plans"]]

    width, height = req["width"], req["height"]
    gen_size = _map_ad_size(width, height)
    brand_color = req.get("brand_color")
    tone = req.get("tone_and_manner")
    improvement_context: str | None = state.get("improvement_context")
    product_image_bytes: bytes | None = state.get("product_image_bytes")

    logo_s3_key = req.get("brand_logo_s3_key")
    logo_image_bytes: bytes | None = None
    if logo_s3_key:
        try:
            logo_image_bytes = await download_bytes(logo_s3_key)
        except Exception:
            logo_image_bytes = None

    done = 0
    gemini = settings.generator_gen_mode == "gemini"

    # 누끼(배경제거)는 상품 있으면 항상 수행 — 후보 3종 공통 1회.
    # gemini 모드는 실제 합성엔 원본 이미지를 멀티모달 입력으로 쓰지만(누끼 미사용),
    # 개선 모드 재사용을 위해 gemini 모드에서도 누끼는 만들어 S3에 저장해둔다.
    product_cutout_bytes: bytes | None = None
    if product_image_bytes is not None:
        try:
            product_cutout_bytes = await remove_product_background(product_image_bytes)
            # 개선 모드에서 재사용할 수 있도록 누끼본을 S3에 보존
            cutout_key = product_cutout_key(generation_id)
            try:
                await upload_bytes(product_cutout_bytes, cutout_key, content_type="image/png")
                logger.info("누끼 이미지 S3 저장 완료: key=%s", cutout_key)
            except Exception:
                logger.warning(
                    "누끼 이미지 S3 저장 실패 — 개선 모드에서 재사용 불가: key=%s", cutout_key
                )
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
            product_image_bytes=product_image_bytes,
            logo_image_bytes=logo_image_bytes,
            gemini=gemini,
            improvement_context=improvement_context,
        )

    # 카피 3개를 텍스트 LLM 1회 호출로 일괄 생성 (두 모드 공통).
    # Gemini 이미지 모델(특히 3-pro)은 카피 텍스트를 자주 누락(이미지만 반환)하므로,
    # 카피는 이미지 모델에 의존하지 않고 항상 텍스트 LLM으로 만든다.
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
        improvement_context=improvement_context,
    )

    async def build(idx: int, variant_id: str, plan: StrategyPlan) -> dict:
        nonlocal done

        if gemini:
            # gemini 모드 — 이미지는 Gemini로 생성(상품 있으면 원본 멀티모달 참조, 픽셀 보존 미보장).
            # 카피는 배치(텍스트 LLM)를 사용 — Gemini 이미지 모델이 카피 텍스트를 자주 누락하기 때문.
            ad_copy = batch_copies[idx]
            image_bytes, _ = await generate_image_and_copy(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
                improvement_context=improvement_context,
                product_image_bytes=product_image_bytes,
            )
        else:
            # openai 모드 — 카피는 이미 배치 생성됨, 이미지만 생성.
            # 상품 이미지가 있으면 마스크 인페인팅으로 상품 픽셀 보존하며 생성.
            ad_copy = batch_copies[idx]
            image_bytes = await generate_image(
                product_analysis=product_analysis,
                strategy=plan.strategy,
                template=plan.template,
                size=gen_size,
                brand_color=brand_color,
                tone=tone,
                product_cutout_bytes=product_cutout_bytes,
                improvement_context=improvement_context,
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
            strategy=plan.strategy,
        )

        # 5. 품질검증 (순수 동기 함수)
        quality_report = check_quality(
            ad_copy=ad_copy,
            target=product_analysis.target_audience,
            product_name=product_analysis.product_name,
        )

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

    # openai 모드에서만 선계산 — 카피가 이미 준비돼 있어 이미지 생성과 병렬로 실행 가능.
    # gemini 모드는 build 내부에서 카피가 만들어지므로 explain 노드가 폴백 처리한다.
    async def _precompute_explanations() -> list[dict]:
        copies = batch_copies
        target = req.get("target_audience") or "기존 타겟"
        product_name = req.get("product_name") or "(개선모드)"
        rows = [
            {
                "template": plan.template,
                "strategy_description": plan.strategy_description,
                "rationale": plan.rationale,
                "headline": copy.headline,
                "qa_passed": check_quality(
                    ad_copy=copy,
                    target=product_analysis.target_audience,
                    product_name=product_analysis.product_name,
                ).overall_passed,
            }
            for plan, copy in zip(plans, copies, strict=True)
        ]
        return await generate_explanations(product_name, target, rows)

    build_coros = [
        build(i, vid, plan) for i, (vid, plan) in enumerate(zip(_VARIANT_IDS, plans, strict=True))
    ]
    explanations: list[dict] | None = None
    if not gemini:
        *results, explanations = await asyncio.gather(*build_coros, _precompute_explanations())
    else:
        results = list(await asyncio.gather(*build_coros))

    candidates = sorted(results, key=lambda c: c["idx"])
    qa_results = [c.pop("_quality_report") for c in candidates]
    out: dict = {"candidates": candidates, "qa_results": qa_results}
    if explanations is not None:
        out["explanations"] = explanations
    return out


async def _generate_improve_candidate(state: GenerationState, config: RunnableConfig) -> dict:
    """개선 모드 전용 — 항상 OpenAI 경로, 누끼 로드, 단일 후보 1장 생성."""
    emit_progress(config, "candidates", 40, "개선 이미지 생성 중...")
    req = state["request"]
    generation_id = state["generation_id"]
    product_analysis = ProductAnalysis(**state["product_analysis"])
    plans = [StrategyPlan(**p) for p in state["plans"]]
    plan = plans[0]  # strategy 노드에서 주입한 더미 플랜 1개

    width, height = req["width"], req["height"]
    gen_size = _map_ad_size(width, height)
    brand_color = req.get("brand_color")
    tone = req.get("tone_and_manner")
    improvement_context: str | None = state.get("improvement_context")

    logo_s3_key = req.get("brand_logo_s3_key")
    logo_image_bytes: bytes | None = None
    if logo_s3_key:
        try:
            logo_image_bytes = await download_bytes(logo_s3_key)
        except Exception:
            logo_image_bytes = None

    # 누끼 이미지 로드 (생성 모드에서 저장된 S3 키)
    product_cutout_s3_key: str | None = req.get("product_cutout_s3_key")
    product_cutout_bytes: bytes | None = None
    if product_cutout_s3_key:
        try:
            product_cutout_bytes = await download_bytes(product_cutout_s3_key)
        except Exception:
            logger.exception(
                "개선 모드 누끼 로드 실패 — 상품 없이 배경 자유 생성으로 진행: key=%s",
                product_cutout_s3_key,
            )

    emit_progress(config, "candidates", 55, "개선 카피 생성 중...")
    ad_copy = await generate_copy(
        product_analysis=product_analysis,
        strategy_output=StrategyOutput(
            strategy=plan.strategy,
            strategy_description=plan.strategy_description,
            rationale=plan.rationale,
        ),
        template=None,
        improvement_context=improvement_context,
    )

    emit_progress(config, "candidates", 68, "개선 이미지 생성 중...")
    image_bytes = await generate_image(
        product_analysis=product_analysis,
        strategy=plan.strategy,
        template=None,
        size=gen_size,
        brand_color=brand_color,
        tone=tone,
        product_cutout_bytes=product_cutout_bytes,
        improvement_context=improvement_context,
        headline="",
        body="",
        cta="",
    )

    base_key = candidate_base_key(generation_id, 0)
    try:
        await upload_bytes(image_bytes, base_key, content_type="image/png")
    except Exception:
        logger.exception("개선 base 이미지 업로드 실패: key=%s", base_key)

    emit_progress(config, "candidates", 82, "텍스트·로고 합성 중...")
    image_bytes = render_ad_text(
        image_bytes,
        headline=ad_copy.headline,
        body=ad_copy.body,
        cta=ad_copy.cta,
        template=None,
        brand_color=brand_color,
        strategy=plan.strategy,
    )

    quality_report = check_quality(
        ad_copy=ad_copy,
        target=product_analysis.target_audience,
        product_name=product_analysis.product_name,
    )

    if logo_image_bytes is not None:
        image_bytes = composite_logo(image_bytes, logo_image_bytes, None)

    s3_key = candidate_key(generation_id, 0)
    await upload_bytes(image_bytes, s3_key, content_type="image/png")
    logger.info("개선 후보 S3 업로드 완료: key=%s", s3_key)

    emit_progress(config, "candidates", 90, "완료")

    candidate = {
        "candidate_id": str(uuid.uuid4()),
        "idx": 0,
        "strategy": {
            "strategy_type": plan.strategy.value,
            "strategy_description": plan.strategy_description,
            "rationale": plan.rationale,
        },
        "template_id": TemplateType.A.value,  # 텍스트 오버레이가 A 폴백이므로 A로 저장
        "copy": ad_copy.model_dump(),
        "image_prompt": None,
        "s3_key": s3_key,
        "requested_size": f"{width}x{height}",
        "rationale": plan.rationale,
    }

    # 개선 모드 설명 — LLM 재호출 없이 고정 텍스트 (explain 노드의 pre 조기반환 활용)
    target = req.get("target_audience") or "기존 타겟"
    _last = target[-1] if target else ""
    _code = ord(_last) - 0xAC00
    particle = "을" if 0 <= _code <= 11171 and _code % 28 != 0 else "를"
    explanations = [
        CandidateExplanation(
            applied_target=f"{target}{particle} 주요 타겟으로 설정",
            applied_strategy=plan.strategy_description,
            applied_template="자유 레이아웃 (개선 모드)",
            rationale="시뮬레이션 피드백과 수정 요청을 반영해 약점을 보완한 새 광고 이미지를 생성했습니다.",
        ).model_dump()
    ]

    return {
        "candidates": [candidate],
        "qa_results": [quality_report.model_dump()],
        "explanations": explanations,
    }
