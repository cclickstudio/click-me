# 멀티모달 단일호출 — Gemini 한 모델이 광고 배경 이미지와 카피(JSON)를 함께 생성
#
# GENERATOR_GEN_MODE=gemini 일 때만 사용. 기본(openai) 경로와 독립.
# 상품 이미지가 있으면 inline_data로 함께 입력해 참조 생성(픽셀 단위 보존은 보장하지 않음).
from __future__ import annotations

import asyncio
import io
import json
import logging
import random
import re

from google import genai
from google.genai import types as genai_types
from google.genai.errors import ClientError, ServerError
from langsmith import traceable
from PIL import Image

from core.config import settings
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import AdCopy, ProductAnalysis

# 전략별 사진 연출 지시 재사용 — openai 경로 전용이 아니라 전략의 시각 정체성 자체라
# gemini 경로도 동일하게 따라야 한다(그동안 여기선 strategy.value 슬러그 한 단어만 넘겨
# "화면을 꽉 채워라" 류 지시가 레이아웃 문구 하나에만 의존해 준수율이 낮았다).
from domain.generator.pipeline.image_generator import (
    _STRATEGY_DESCRIPTIONS,
    _STRATEGY_PHOTO_STYLE,
)

# 같은 도메인 pipeline 내부 헬퍼 재사용 — 비율 매핑·LangSmith usage 수동 기록.
from domain.generator.pipeline.image_providers import (
    _GEMINI_NATIVE_ASPECT_RATIO,
    _record_genai_usage,
)
from domain.generator.pipeline.style_profile import get_style
from tools.utils import str_or_none

logger = logging.getLogger("clickme")


def _detect_mime(data: bytes) -> str:
    fmt = Image.open(io.BytesIO(data)).format or "PNG"
    return {"JPEG": "image/jpeg", "WEBP": "image/webp"}.get(fmt, "image/png")


# text_overlay는 전략의 StyleProfile.text_style=="box"일 때만 실제로 패널을 그린다(그 외
# floating/emotional은 패널 없이 사진 위에 텍스트를 바로 얹힌다). 패널이 없는 전략인데도
# "그 자리는 비워둔다"고 안내하면 실제로 아무것도 안 덮을 빈 공간이 남아 사진이 영역을
# 못 채운 것처럼 보인다 — style_key(box/floating/emotional)로 지시를 나눈다. floating(social_proof)
# 과 emotional은 둘 다 패널이 없다는 점은 같지만, emotional은 "여백·잔잔한 분위기"가 핵심 전략이라
# floating과 똑같이 "꽉 채워라"고만 하면 두 전략의 시각적 차이가 사라진다 — emotional은 별도로
# "여백은 유지하되 완전히 빈 캔버스는 안 된다"로 지시한다.
_TEMPLATE_LAYOUT: dict[TemplateType, dict[str, str]] = {
    TemplateType.A: {
        "box": (
            "제품 장면을 화면 상단 55% 전체에 위·좌·우 가장자리까지 빈틈없이 꽉 채워 배치한다"
            "(그 안에 빈 여백이나 배경만 남는 공간 금지). 하단 45%는 텍스트가 올라갈 영역이므로 비워둔다."
        ),
        "floating": (
            "텍스트 패널이 없으므로(문구는 사진 위에 적응형 색상·그림자로 직접 얹힌다) 제품 장면을 "
            "화면 전체(위·아래·좌·우 가장자리)까지 빈틈없이 꽉 채워 배치한다. 하단 45%도 실제 장면으로 "
            "채우되, 문구 가독성을 위해 그 부분만 상대적으로 차분하고 덜 복잡하게 연출한다. 빈 여백이나 "
            "배경만 남는 공간은 금지."
        ),
    },
    TemplateType.B: {
        "box": (
            "제품을 화면 상단 68% 전체에 위·좌·우 가장자리까지 빈틈없이 역동적으로 크게 채워 배치한다"
            "(빈 여백 금지). 하단 32%는 텍스트 배너 영역이므로 비운다."
        ),
        "floating": (
            "텍스트 배너 패널이 없으므로(문구는 사진 위에 적응형 색상·그림자로 직접 얹힌다) 제품을 "
            "화면 전체(위·아래·좌·우 가장자리)까지 빈틈없이 역동적으로 크게 채워 배치한다. 하단 32%도 "
            "실제 장면으로 채우되, 문구 가독성을 위해 그 부분만 상대적으로 차분하게 연출한다. 빈 여백 금지."
        ),
    },
    TemplateType.C: {
        "box": (
            "우측 47% 영역 전체를 제품·감성 이미지로 위에서 아래까지, 오른쪽 가장자리까지 빈틈없이 꽉 채운다"
            "(사진이 영역 안에서 작게 떠 있거나 위아래로 여백이 남지 않게 한다). "
            "좌측 46%는 텍스트 패널 영역이므로 비운다."
        ),
        "floating": (
            "텍스트 패널이 없으므로(문구는 사진 위에 적응형 색상·그림자로 직접 얹힌다) 제품·감성 이미지를 "
            "화면 전체(좌·우·상·하 가장자리)까지 빈틈없이 꽉 채운다. 좌측 46%도 실제 장면으로 채우되, "
            "문구 가독성을 위해 그 부분만 상대적으로 차분하고 덜 복잡하게 연출한다(낮은 대비, 부드러운 "
            "보케 등). 제품·피사체는 화면 왼쪽에서 65~75% 지점에 오도록 살짝 오른쪽에 배치한다. 빈 여백 금지."
        ),
        "emotional": (
            "텍스트 패널이 없으므로(문구는 사진 위에 적응형 색상·그림자로 직접 얹힌다) 이 전략은 여백과 "
            "잔잔한 분위기가 핵심이다 — 제품을 크고 뚜렷하게 강조하기보다, 은은한 자연광·부드러운 보케·"
            "따뜻한 톤으로 감성적인 여백을 살린다. 다만 화면 전체(좌·우·상·하 가장자리)가 그 잔잔한 "
            "분위기 자체로는 이어져야 하며, 아무 것도 없는 밋밋한 빈 공간이 남으면 안 된다. 좌측 46%는 "
            "특히 차분하고 여백감 있게 유지하고, 제품·피사체는 화면 왼쪽에서 70~85% 지점에 작고 은은하게 "
            "배치한다."
        ),
    },
}

_PROMPT_TEMPLATE = """\
당신은 한국 시장용 광고 크리에이티브를 만드는 디자이너입니다.
아래 정보로 광고 **배경 이미지 1장**을 생성하세요.
중요: 이미지 안에 글자·문자·숫자를 절대 넣지 마세요. 텍스트는 이후 별도로 합성됩니다.

제품/서비스: "{product_name}" (이 이름 자체를 이미지 안에 글자로 쓰지 말 것)
핵심 가치: {core_values}
혜택: {benefits}
타겟: {target_audience}
전략: {strategy}
레이아웃: {layout}
브랜드 컬러 톤: {brand_color} (이 코드 값을 텍스트로 표시하지 말고 배경 색감에만 반영할 것)
톤앤매너: {tone}
{improvement_section}
규칙:
- 글자·문자·숫자·타이포그래피·워터마크·로고·QR 일절 금지 (순수 배경+제품 이미지).
- 제품명·브랜드명·색상 코드(HEX)를 이미지 위에 텍스트·라벨·워터마크 형태로 표시하는 것 절대 금지.
- 레이아웃에 명시된 텍스트 영역은 깨끗이 비워둔다.
- 이미지와 함께, 사용할 카피를 다음 JSON 한 줄로 출력하세요:
  {{"headline": "...(20자 이내)", "body": "...(50자 이내)", "cta": "...(10자 이내)"}}
- 카피는 오탈자·비문 없는 자연스러운 한국어."""

_IMPROVE_SECTION = """
개선 방향 (최우선 반영): {improvement_context}
기존 광고의 문제를 해결하는 방향으로 배경과 카피를 구성하세요.
"""

# 상품 이미지가 함께 입력될 때 덧붙이는 지시 — 첨부 상품을 참조해 배치.
_PRODUCT_IMAGE_SECTION = """
첨부된 상품 이미지를 참고하여, 동일한 상품이 자연스럽게 보이도록 배경에 배치하세요.
상품의 형태·색·로고를 최대한 유지하되, 이미지 안에 글자는 넣지 마세요.
"""

# 기존 광고 이미지가 함께 입력될 때(개선 모드) 덧붙이는 지시 — 기존 디자인을 참조해 개선.
_EXISTING_AD_SECTION = """
첨부된 기존 광고 이미지를 참고하여, 전반적인 구도·분위기의 장점은 살리되 개선 방향을 반영한
더 나은 광고 배경을 생성하세요. 기존 광고의 글자는 무시하고(이미지 안에 글자는 넣지 않음) 배경만 다룹니다.
"""


def _build_prompt(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    brand_color: str | None,
    tone: str | None,
    improvement_context: str | None = None,
    has_product_image: bool = False,
    has_existing_ad: bool = False,
) -> str:
    improvement_section = (
        _IMPROVE_SECTION.format(improvement_context=improvement_context)
        if improvement_context
        else ""
    )
    strategy_guide = f"{_STRATEGY_DESCRIPTIONS[strategy]}. {_STRATEGY_PHOTO_STYLE[strategy]}"
    style_key = get_style(strategy).text_style
    # A/B는 emotional 전략이 실제로 배정되지 않으므로(template_selector가 emotional→C로만
    # 매핑) emotional 키가 없다 — 방어적 폴백으로 floating과 동일하게 처리.
    layout_variants = _TEMPLATE_LAYOUT[template]
    prompt = _PROMPT_TEMPLATE.format(
        product_name=product_analysis.product_name,
        core_values=", ".join(product_analysis.core_values) or "-",
        benefits=", ".join(product_analysis.benefits) or "-",
        target_audience=product_analysis.target_audience or "일반 소비자",
        strategy=strategy_guide,
        layout=layout_variants.get(style_key, layout_variants["floating"]),
        brand_color=brand_color or "지정 없음",
        tone=tone or "깔끔하고 신뢰감 있게",
        improvement_section=improvement_section,
    )
    if has_product_image:
        prompt += "\n" + _PRODUCT_IMAGE_SECTION
    if has_existing_ad:
        prompt += "\n" + _EXISTING_AD_SECTION
    return prompt


# Gemini 이미지 모델은 동시 호출이 겹치면 503·이미지누락이 급증한다 → 전역 동시 호출 수 제한.
# (후보 3종이 asyncio.gather로 동시에 때리는 것을 직렬화해 과부하를 막는다. 필요 시 상향.)
_MAX_CONCURRENT = 1
_semaphore = asyncio.Semaphore(_MAX_CONCURRENT)

# 이미지 누락·503 대비 재시도 백오프(초) — 지터를 더해 병렬 재시도 동기화를 방지.
_RETRY_BACKOFF = [3, 6, 10]


async def _generate_once(
    client: genai.Client, contents: list, size: AdSize
) -> tuple[bytes, AdCopy] | None:
    """Gemini 1회 호출 — 이미지+카피를 파싱해 반환. 이미지가 없으면 None(재시도 신호)."""
    response = await client.aio.models.generate_content(
        model=settings.generator_gemini_image_model,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=genai_types.ImageConfig(aspect_ratio=_GEMINI_NATIVE_ASPECT_RATIO[size]),
        ),
    )
    _record_genai_usage(response, settings.generator_gemini_image_model)

    if not response.candidates:
        logger.warning(
            "멀티모달 응답에 candidates 없음: model=%s prompt_feedback=%s",
            settings.generator_gemini_image_model,
            getattr(response, "prompt_feedback", None),
        )
        return None
    image_bytes: bytes | None = None
    text_parts: list[str] = []
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            image_bytes = part.inline_data.data
        elif part.text:
            text_parts.append(part.text)
    if not image_bytes:
        logger.warning(
            "멀티모달 응답에 이미지 없음: model=%s finish_reason=%s text=%r",
            settings.generator_gemini_image_model,
            getattr(response.candidates[0], "finish_reason", None),
            "\n".join(text_parts)[:500],
        )
        return None

    raw = _parse_copy_json("\n".join(text_parts))
    ad_copy = AdCopy(
        headline=str_or_none(raw.get("headline")) or "",
        body=str_or_none(raw.get("body")) or "",
        cta=str_or_none(raw.get("cta")) or "지금 바로 확인하기",
    )
    return image_bytes, ad_copy


@traceable(
    name="generator:generate_multimodal",
    metadata={"pipeline": "generator", "prompt_version": "v2.0-gemini"},
)
async def generate_image_and_copy(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    size: AdSize = AdSize.SQUARE,
    brand_color: str | None = None,
    tone: str | None = None,
    improvement_context: str | None = None,
    product_image_bytes: bytes | None = None,
    existing_ad_bytes: bytes | None = None,
) -> tuple[bytes, AdCopy]:
    """Gemini 한 번의 호출로 광고 배경 이미지 + 카피를 생성한다.

    상품 이미지(생성) 또는 기존 광고 이미지(개선)가 있으면 inline_data로 함께 입력해 참조 생성
    (픽셀 보존은 보장 안 됨). 이미지엔 글자를 넣지 않으며(프롬프트 지시), 카피는 호출자가 PIL로 합성한다.
    Gemini가 간헐적으로 이미지를 빠뜨리거나(텍스트만) 503(과부하)을 내므로, 전역 동시 호출을
    제한(_semaphore)하고 지터 백오프로 재시도한다.
    """
    prompt = _build_prompt(
        product_analysis,
        strategy,
        template,
        brand_color,
        tone,
        improvement_context,
        has_product_image=product_image_bytes is not None,
        has_existing_ad=existing_ad_bytes is not None,
    )

    contents: list = [prompt]
    if product_image_bytes is not None:
        contents.append(
            genai_types.Part.from_bytes(
                data=product_image_bytes, mime_type=_detect_mime(product_image_bytes)
            )
        )
    if existing_ad_bytes is not None:
        contents.append(
            genai_types.Part.from_bytes(
                data=existing_ad_bytes, mime_type=_detect_mime(existing_ad_bytes)
            )
        )

    client = genai.Client(api_key=settings.gemini_api_key)
    # 동시 호출 제한 — 후보 3종 동시 생성 시 과부하로 인한 503·이미지누락을 막는다.
    async with _semaphore:
        for attempt in range(len(_RETRY_BACKOFF) + 1):
            try:
                result = await _generate_once(client, contents, size)
            except ServerError:
                # 503 등 5xx 과부하 — 일시적. 마지막 시도면 원예외 전파.
                if attempt >= len(_RETRY_BACKOFF):
                    raise
                result = None
            except ClientError as exc:
                # 429(RateLimit)만 일시적 — 나머지 4xx(400 등)는 재시도 무의미하므로 즉시 전파.
                if getattr(exc, "code", None) != 429 or attempt >= len(_RETRY_BACKOFF):
                    raise
                result = None
            if result is not None:
                return result
            if attempt < len(_RETRY_BACKOFF):
                await asyncio.sleep(_RETRY_BACKOFF[attempt] + random.uniform(0, 1.5))
    raise RuntimeError("멀티모달 응답에 이미지가 없습니다 (재시도 소진).")


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
