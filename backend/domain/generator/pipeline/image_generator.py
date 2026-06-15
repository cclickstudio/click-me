import base64
import io

from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.schemas import ProductAnalysis

# OpenAI 클라이언트 초기화 (이미지 생성 API 호출에 사용)
_client = AsyncOpenAI(timeout=120.0)

# ─────────────────────────────────────────────────────────────────────────────
# 전략별 메타데이터 매핑 (광고 전략 → 프롬프트 설명문)
# 각 AdStrategy 값에 대응하는 영문 설명을 담아 프롬프트에 삽입한다.
# ─────────────────────────────────────────────────────────────────────────────
_STRATEGY_DESCRIPTIONS: dict[AdStrategy, str] = {
    AdStrategy.BENEFIT: "highlighting product benefits and value proposition",
    AdStrategy.PROBLEM_SOLVING: "showing how the product solves customer pain points",
    AdStrategy.SOCIAL_PROOF: "emphasizing trust, reviews, and social credibility",
    AdStrategy.EMOTIONAL: "evoking emotions and emotional connection with the brand",
    AdStrategy.FOMO: "creating urgency and FOMO with limited-time messaging",
}

# 전략별 사진 촬영 스타일 지시문
# 조명, 배경, 분위기 등 사진적 연출 방향을 전략에 맞게 정의한다.
_STRATEGY_PHOTO_STYLE: dict[AdStrategy, str] = {
    AdStrategy.BENEFIT: (
        "Clean, well-lit product photography with soft even shadows. "
        "Bright, optimistic lighting that showcases product details and quality."
    ),
    AdStrategy.PROBLEM_SOLVING: (
        "Contrast lighting transitioning from dark to bright, symbolizing transformation. "
        "Clean background with the product as the clear solution focal point."
    ),
    AdStrategy.SOCIAL_PROOF: (
        "Warm, natural lifestyle photography suggesting authentic everyday use. "
        "Approachable, inviting atmosphere with real-world context."
    ),
    AdStrategy.EMOTIONAL: (
        "Soft bokeh background, warm golden tones, shallow depth of field. "
        "Cinematic quality evoking aspiration, comfort, and emotional resonance."
    ),
    AdStrategy.FOMO: (
        "Bold, high-energy, dramatic lighting with strong contrast. "
        "Vibrant colors and dynamic composition creating urgency and excitement."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# 템플릿별 레이아웃 스타일 & 안전 영역(Safe Zone) 정의
# ─────────────────────────────────────────────────────────────────────────────

# 템플릿 유형(A/B/C)에 따른 전반적인 시각 스타일을 정의한다.
_TEMPLATE_STYLE: dict[TemplateType, str] = {
    TemplateType.A: (
        "Clean product photography style. "
        "Product centered and prominent against a simple, uncluttered background. "
        "Neutral or softly colored backdrop that makes the product stand out."
    ),
    TemplateType.B: (
        "Dynamic product shot with energy and visual impact. "
        "Product clearly visible and centered, with a vibrant or bold background. "
        "Eye-catching composition suitable for promotional advertising."
    ),
    TemplateType.C: (
        "Rich lifestyle or brand imagery with atmospheric depth. "
        "Product shown in a real-world context or elegant setting. "
        "Cinematic quality, horizontally centered subject — edges may be cropped in final use."
    ),
}

# 텍스트 오버레이가 가려질 영역을 AI에게 알려주는 Safe Zone 지시문.
# 각 템플릿은 텍스트 배너 위치가 다르므로, 제품이 가리지 않도록 구도를 유도한다.
_TEMPLATE_SAFE_ZONES: dict[TemplateType, str] = {
    TemplateType.A: (
        "COMPOSITION RULE: Keep the bottom 38% of the frame visually minimal and uncluttered "
        "— this zone will be covered by a semi-transparent text overlay. "
        "Place the product in the upper 55% of the frame."
    ),
    TemplateType.B: (
        "COMPOSITION RULE: Keep the top 17% and bottom 24% of the frame clear and uncluttered "
        "— these zones will be covered by solid color text banners. "
        "Place the product prominently in the middle 59% of the frame."
    ),
    TemplateType.C: (
        "COMPOSITION RULE: Place ALL important visual elements in the RIGHT 58% of the frame. "
        "The left 42% will be completely covered by a solid color panel — keep it simple or empty. "
        "Product must be clearly visible on the right side."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# 이미지 생성 프롬프트 템플릿
# 위에서 정의한 스타일·전략 값들이 format()으로 조합되어 최종 프롬프트를 구성한다.
# ─────────────────────────────────────────────────────────────────────────────
_PROMPT_TEMPLATE = """\
Create a professional {platform} advertisement product image.
THIS IS A PRODUCT-ONLY IMAGE — do NOT include any text, letters, words, or numbers.

Visual style: {style}
Photography style: {photo_style}
Strategy: {strategy_desc}

Product: {product_name}
{core_values_line}Target audience: {target_audience}
{color_line}
{tone_line}

Product-specific visual direction:
{product_visual_context}

{safe_zone}

Requirements:
- High-quality, commercial advertising photography or illustration
- STRICTLY NO text, letters, words, numbers, or typography of any kind
- No logos, watermarks, URLs, or QR codes
- Product must be clearly visible and well-lit
- Clean, modern aesthetic suitable for Meta/Instagram feed
- Photo-realistic or high-quality illustration style"""

# 직접 수정 모드에서 원본 이미지를 Edit API로 수정할 때 사용하는 프롬프트
_EDIT_PROMPT_TEMPLATE = """\
Modify this advertisement image to improve it based on the following direction.
Do NOT add any text, letters, words, or numbers to the image.

Strategy: {strategy_desc}
Visual style: {style}
{color_line}
{tone_line}

Improvement direction:
{improvement_context}

{safe_zone}

Requirements:
- Keep the overall composition and product recognizable
- STRICTLY NO text, letters, words, numbers, or typography
- Maintain high-quality, commercial advertising photography style
- Adjust lighting, color, mood, or composition as needed"""


# ─────────────────────────────────────────────────────────────────────────────
# 제품 분석 결과를 시각적 방향 문장으로 변환하는 헬퍼
# 브랜드 가치, 혜택, 브랜드 컬러를 조합해 프롬프트 내 시각 방향 섹션을 생성한다.
# ─────────────────────────────────────────────────────────────────────────────
def _build_product_visual_context(
    product_analysis: ProductAnalysis,
    brand_color: str | None,
) -> str:
    lines = []

    if product_analysis.core_values:
        values_str = ", ".join(product_analysis.core_values)
        lines.append(
            f"Background atmosphere and mood must reflect these brand values: {values_str}"
        )

    if product_analysis.benefits:
        benefits_str = ", ".join(product_analysis.benefits[:3])
        lines.append(f"The visual should evoke the feeling of: {benefits_str}")

    if brand_color:
        lines.append(
            f"The entire background color palette must be built around {brand_color}. "
            "Use it as the dominant hue for the scene, lighting, and atmospheric elements."
        )

    return (
        "\n".join(lines)
        if lines
        else "Use a visually appealing background that complements the product."
    )


# ─────────────────────────────────────────────────────────────────────────────
# 메인 이미지 생성 함수 (LangSmith 추적 활성화)
# 전략·템플릿·사이즈 등 입력값을 받아 프롬프트를 조립하고,
# GPT Image API를 호출한 뒤 base64 디코딩된 이미지 bytes를 반환한다.
# ─────────────────────────────────────────────────────────────────────────────
@traceable(name="ImageGenerator", metadata={"pipeline": "generator"})
async def generate_image(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    size: AdSize = AdSize.SQUARE,
    brand_color: str | None = None,
    tone: str | None = None,
    original_image_bytes: bytes | None = None,
    improvement_context: str | None = None,
) -> bytes:
    color_line = (
        f"Brand color accent: {brand_color} — incorporate into highlights and secondary elements"
        if brand_color
        else "Color palette: modern, clean, professional"
    )
    tone_line = f"Tone and manner: {tone}" if tone else "Tone: clean, professional, trustworthy"

    # 직접 수정 모드: 원본 이미지 + Edit API
    if original_image_bytes is not None:
        prompt = _EDIT_PROMPT_TEMPLATE.format(
            strategy_desc=_STRATEGY_DESCRIPTIONS[strategy],
            style=_TEMPLATE_STYLE[template],
            color_line=color_line,
            tone_line=tone_line,
            improvement_context=improvement_context or "전반적인 광고 품질을 개선하세요.",
            safe_zone=_TEMPLATE_SAFE_ZONES[template],
        )
        image_file = io.BytesIO(original_image_bytes)
        image_file.name = "original.png"
        response = await _client.images.edit(
            model="gpt-image-1",
            image=image_file,
            prompt=prompt,
            n=1,
            size=size.value,
        )
        return base64.b64decode(response.data[0].b64_json)

    # 시뮬레이션 기반 개선 또는 생성 모드: Generate API
    core_values_line = (
        f"Core values: {', '.join(product_analysis.core_values)}\n"
        if product_analysis.core_values
        else ""
    )
    target_audience = product_analysis.target_audience or "general audience"
    product_visual_context = _build_product_visual_context(product_analysis, brand_color)

    improvement_line = (
        f"\nImprovement direction (apply to visual):\n{improvement_context}"
        if improvement_context
        else ""
    )

    prompt = _PROMPT_TEMPLATE.format(
        platform="Meta/Instagram",
        style=_TEMPLATE_STYLE[template],
        photo_style=_STRATEGY_PHOTO_STYLE[strategy],
        strategy_desc=_STRATEGY_DESCRIPTIONS[strategy],
        product_name=product_analysis.product_name,
        core_values_line=core_values_line,
        target_audience=target_audience,
        color_line=color_line,
        tone_line=tone_line,
        product_visual_context=product_visual_context + improvement_line,
        safe_zone=_TEMPLATE_SAFE_ZONES[template],
    )

    response = await _client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        n=1,
        size=size.value,
        quality="high",
    )

    return base64.b64decode(response.data[0].b64_json)
