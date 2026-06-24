# 멀티모달 단일호출 — 한 모델이 광고 이미지(카피 렌더링 포함)와 카피 텍스트를 함께 생성
#
# GENERATOR_GEN_MODE=multimodal 일 때만 사용. 기본(pipeline) 경로와 독립.
# ⚠️ OpenAI Responses API의 image_generation 툴 경로는 실 키로 런타임 검증이 필요한 스파이크다.
from __future__ import annotations

import base64
import json
import re

from langsmith import traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from core.config import settings
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import AdCopy, ProductAnalysis
from tools.utils import str_or_none

# wrap_openai로 감싸 Responses API(이미지+카피) 호출 usage가 LangSmith에 기록되게 한다.
_client = wrap_openai(AsyncOpenAI(timeout=settings.generator_image_timeout))

_TEMPLATE_LAYOUT: dict[TemplateType, str] = {
    TemplateType.A: "제품을 화면 상단~중앙에 크게 배치하고, 하단 45%는 텍스트가 올라갈 영역이므로 비워둔다.",
    TemplateType.B: "상단 20%와 하단 40%는 텍스트 띠 영역이므로 비우고, 중앙에 제품을 배치한다.",
    TemplateType.C: "좌측 46%는 텍스트 패널 영역이므로 비우고, 우측에 제품·감성 이미지를 배치한다.",
}

_PROMPT_TEMPLATE = """\
당신은 한국 시장용 광고 크리에이티브를 만드는 디자이너입니다.
아래 정보로 광고 **배경 이미지 1장**을 생성하세요.
중요: 이미지 안에 글자·문자·숫자를 절대 넣지 마세요. 텍스트는 이후 별도로 합성됩니다.

제품: {product_name}
핵심 가치: {core_values}
혜택: {benefits}
타겟: {target_audience}
전략: {strategy}
레이아웃: {layout}
브랜드 컬러: {brand_color}
톤앤매너: {tone}
{improvement_section}
규칙:
- 글자·문자·숫자·타이포그래피·워터마크·로고·QR 일절 금지 (순수 배경+제품 이미지).
- 레이아웃에 명시된 텍스트 영역은 깨끗이 비워둔다.
- 이미지와 함께, 사용할 카피를 다음 JSON 한 줄로 출력하세요:
  {{"headline": "...(20자 이내)", "body": "...(50자 이내)", "cta": "...(10자 이내)"}}
- 카피는 오탈자·비문 없는 자연스러운 한국어."""

_IMPROVE_SECTION = """
개선 방향 (최우선 반영): {improvement_context}
기존 광고의 문제를 해결하는 방향으로 배경과 카피를 구성하세요.
"""


def _build_prompt(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    brand_color: str | None,
    tone: str | None,
    improvement_context: str | None = None,
) -> str:
    improvement_section = (
        _IMPROVE_SECTION.format(improvement_context=improvement_context)
        if improvement_context
        else ""
    )
    return _PROMPT_TEMPLATE.format(
        product_name=product_analysis.product_name,
        core_values=", ".join(product_analysis.core_values) or "-",
        benefits=", ".join(product_analysis.benefits) or "-",
        target_audience=product_analysis.target_audience or "일반 소비자",
        strategy=strategy.value,
        layout=_TEMPLATE_LAYOUT[template],
        brand_color=brand_color or "지정 없음",
        tone=tone or "깔끔하고 신뢰감 있게",
        improvement_section=improvement_section,
    )


@traceable(
    name="generator:generate_multimodal",
    metadata={"pipeline": "generator", "prompt_version": "v1.0"},
)
async def generate_image_and_copy(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    size: AdSize = AdSize.SQUARE,
    brand_color: str | None = None,
    tone: str | None = None,
    improvement_context: str | None = None,
) -> tuple[bytes, AdCopy]:
    """한 번의 모델 호출로 완성형 광고 이미지 + 카피를 생성한다.

    현재 openai(Responses API image_generation 툴)만 구현. 그 외 프로바이더는 NotImplementedError.
    """
    provider = settings.generator_multimodal_provider
    if provider != "openai":
        raise NotImplementedError(f"멀티모달 미지원 프로바이더: {provider!r} (현재 openai만 구현)")

    prompt = _build_prompt(
        product_analysis, strategy, template, brand_color, tone, improvement_context
    )

    response = await _client.responses.create(
        model=settings.generator_multimodal_model,
        input=prompt,
        tools=[
            {
                "type": "image_generation",
                "size": size.value,
                "model": settings.generator_multimodal_image_model,
            }
        ],
    )

    image_b64: str | None = None
    text_parts: list[str] = []
    for item in response.output:
        item_type = getattr(item, "type", None)
        if item_type == "image_generation_call":
            image_b64 = getattr(item, "result", None)
        elif item_type == "message":
            for block in getattr(item, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    text_parts.append(text)

    if not image_b64:
        raise RuntimeError("멀티모달 응답에 이미지가 없습니다.")

    raw = _parse_copy_json("\n".join(text_parts))
    ad_copy = AdCopy(
        headline=str_or_none(raw.get("headline")) or "",
        body=str_or_none(raw.get("body")) or "",
        cta=str_or_none(raw.get("cta")) or "지금 바로 확인하기",
    )
    return base64.b64decode(image_b64), ad_copy


def _parse_copy_json(text: str) -> dict:
    """모델 응답(산문 + JSON 혼합 가능)에서 카피 JSON 객체를 방어적으로 추출."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}
