"""노드 4 — 광고 후보 3종 생성: 카피 → 이미지(gpt-image-1) → S3 업로드."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langsmith import traceable
from openai import AsyncOpenAI

from core.config import settings
from domain.generator.contracts.schemas import AdCopy
from domain.generator.contracts.templates import AdTemplate, get_template, map_image_size
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from tools.storage.s3 import candidate_key, upload_bytes

_copy_llm = ChatOpenAI(
    model=settings.generator_text_model,
    api_key=settings.openai_api_key,
    temperature=0.7,
).with_structured_output(AdCopy)

_image_client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=180.0)

_COPY_SYSTEM = """당신은 광고 카피라이터입니다. 전략과 템플릿 구조에 맞는 한국어 광고 카피를 작성하세요.
- headline: 15자 이내의 강렬한 헤드라인
- subcopy: 25자 이내의 보조 문구
- benefit_text: 30자 이내의 혜택/이벤트 문구
- cta: 10자 이내의 행동 유도 문구 (예: 지금 구매하기)
짧고 명확하게, 이미지에 렌더링하기 좋은 문구로 작성하세요."""


def build_image_prompt(req: dict, strategy: dict, template: AdTemplate, copy: AdCopy) -> str:
    """템플릿 레이아웃 + 카피 + 브랜드 옵션을 gpt-image-1 프롬프트로 조립."""
    brand_lines = []
    if req.get("brand_color"):
        brand_lines.append(f"- 브랜드 메인 컬러 {req['brand_color']}를 배경·포인트 컬러로 사용")
    if req.get("tone_and_manner"):
        brand_lines.append(f"- 톤앤매너: {req['tone_and_manner']}")
    if req.get("brand_logo_url"):
        brand_lines.append("- Logo Area에 심플한 브랜드 로고 형태 배치")
    brand_block = "\n".join(brand_lines) if brand_lines else "- 제품 특성에 어울리는 세련된 색감"

    return f"""고품질 Instagram 피드 광고 이미지를 생성하세요.

## 제품
{req["product_name"]} — {req["product_description"][:300]}

## 광고 전략
{strategy["name"]}: {strategy["key_message"]}

## 레이아웃 (Template {template.template_id} {template.name} — 이미지 크기 대비 % 좌표, 반드시 준수)
{template.layout_prompt()}
- 모든 요소는 상하좌우 5% Safe Area 안쪽에 배치

## 텍스트 (아래 한국어 문구를 철자 그대로 정확히 렌더링 — 오타·변형 금지)
- 헤드라인: "{copy.headline}"
- 보조 문구: "{copy.subcopy}"
- 혜택 문구: "{copy.benefit_text}"
- CTA 버튼: "{copy.cta}"

## 브랜드·스타일
{brand_block}
- 전문 광고 디자인 품질, 선명하고 가독성 높은 한글 타이포그래피"""


@traceable(name="AdImageGeneration")
async def generate_image(prompt: str, size: str) -> bytes:
    """gpt-image-1로 광고 이미지 생성 (PNG 바이트 반환)."""
    response = await _image_client.images.generate(
        model=settings.generator_image_model,
        prompt=prompt,
        size=size,
        quality=settings.generator_image_quality,
        n=1,
    )
    return base64.b64decode(response.data[0].b64_json)


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
            image_bytes = await generate_image(image_prompt, size)

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
