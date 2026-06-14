"""노드 4 — 광고 후보 3종 생성: 카피 → 이미지(gpt-image-1) → S3 업로드."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid

from langchain_core.runnables import RunnableConfig
from langsmith import traceable
from openai import AsyncOpenAI

from core.config import settings
from domain.generator.contracts.schemas import AdCopy
from domain.generator.contracts.templates import AdTemplate, get_template, map_image_size
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.llm.factory import build_text_llm
from domain.generator.render.text_overlay import compose_ad_image
from tools.storage.s3 import candidate_key, upload_bytes

_copy_llm = build_text_llm(temperature=0.7).with_structured_output(AdCopy)

_image_client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=180.0)

_COPY_SYSTEM = """당신은 광고 카피라이터입니다. 전략과 템플릿 구조에 맞는 한국어 광고 카피를 작성하세요.
- headline: 15자 이내의 강렬한 헤드라인
- subcopy: 25자 이내의 보조 문구
- benefit_text: 30자 이내의 혜택/이벤트 문구
- cta: 10자 이내의 행동 유도 문구 (예: 지금 구매하기)
짧고 명확하게, 이미지에 렌더링하기 좋은 문구로 작성하세요."""


def build_image_prompt(req: dict, strategy: dict, template: AdTemplate, copy: AdCopy) -> str:
    """텍스트 없는 배경/제품 이미지 프롬프트 조립 — 카피는 후처리(Pillow)로 합성한다."""
    brand_lines = []
    if req.get("brand_color"):
        brand_lines.append(f"- 브랜드 메인 컬러 {req['brand_color']}를 배경·포인트 컬러로 사용")
    if req.get("tone_and_manner"):
        brand_lines.append(f"- 톤앤매너: {req['tone_and_manner']}")
    brand_block = "\n".join(brand_lines) if brand_lines else "- 제품 특성에 어울리는 세련된 색감"

    product_area = template.area_by_role("product")
    product_pos = (
        f"가로 {product_area.x[0]}~{product_area.x[1]}%, 세로 {product_area.y[0]}~{product_area.y[1]}%"
        if product_area
        else "중앙"
    )

    return f"""고품질 Instagram 피드 광고용 **배경 이미지**를 생성하세요. 글자·텍스트·로고는 절대 넣지 마세요.

## 제품
{req["product_name"]} — {req["product_description"][:300]}

## 분위기/전략
{strategy["name"]}: {strategy["key_message"]}

## 구성 (중요)
- 제품/주요 비주얼은 {product_pos} 영역에 배치
- 상단(헤드라인 영역)과 하단(혜택·CTA 영역)은 나중에 텍스트를 얹으므로 **여백/단순한 배경**으로 비워둘 것
- 어떤 문자·숫자·글자·워터마크·로고도 렌더링하지 말 것 (텍스트는 후처리로 합성됨)

## 브랜드·스타일
{brand_block}
- 전문 광고 디자인 품질, 깔끔하고 고급스러운 비주얼"""


async def _openai_generate_image(prompt: str, size: str) -> bytes:
    response = await _image_client.images.generate(
        model=settings.generator_image_model,
        prompt=prompt,
        size=size,
        quality=settings.generator_image_quality,
        n=1,
    )
    return base64.b64decode(response.data[0].b64_json)


@traceable(name="AdImageGeneration")
async def generate_image(prompt: str, size: str) -> bytes:
    """이미지 프로바이더 디스패치 — 현재 openai(gpt-image-1)만 구현. PNG 바이트 반환."""
    provider = settings.generator_image_provider
    if provider == "openai":
        return await _openai_generate_image(prompt, size)
    raise NotImplementedError(f"지원하지 않는 이미지 프로바이더: {provider}")


async def generate_candidates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "candidates", 40, "광고 후보 생성 중 (0/3)")
    req = state["request"]
    size = map_image_size(req["width"], req["height"])
    sem = asyncio.Semaphore(3)
    done = 0

    async def build(idx: int, strategy: dict, assignment: dict) -> dict:
        nonlocal done
        async with sem:
            template = get_template(assignment["template_id"])
            copy_prompt = (
                f"제품명: {req['product_name']}\n"
                f"타겟: {req['target_audience']}\n"
                f"전략: {json.dumps(strategy, ensure_ascii=False)}\n"
                f"템플릿: {template.name} — {template.description}\n"
                f"상품 분석: {json.dumps(state['product_analysis'], ensure_ascii=False)}"
            )
            copy: AdCopy = await _copy_llm.ainvoke(
                [("system", _COPY_SYSTEM), ("user", copy_prompt)]
            )

            image_prompt = build_image_prompt(req, strategy, template, copy)
            background_bytes = await generate_image(image_prompt, size)

            # 카피는 모델이 아니라 코드로 합성 (한글 깨짐 방지)
            image_bytes = await asyncio.to_thread(
                compose_ad_image, background_bytes, copy, template, req.get("brand_color")
            )

            s3_key = candidate_key(state["generation_id"], idx)
            await upload_bytes(image_bytes, s3_key, content_type="image/png")

            done += 1
            emit_progress(config, "candidates", 40 + done * 12, f"광고 후보 생성 중 ({done}/3)")
            return {
                "candidate_id": str(uuid.uuid4()),
                "idx": idx,
                "strategy": strategy,
                "template_id": template.template_id,
                "template_reason": assignment.get("reason", ""),
                "copy": copy.model_dump(),
                "image_prompt": image_prompt,
                "s3_key": s3_key,
                "requested_size": f"{req['width']}x{req['height']}",
                "actual_size": size,
            }

    pairs = list(zip(state["strategies"], state["template_assignments"], strict=True))
    candidates = await asyncio.gather(
        *[build(i, strategy, assignment) for i, (strategy, assignment) in enumerate(pairs)]
    )
    return {"candidates": sorted(candidates, key=lambda c: c["idx"])}
