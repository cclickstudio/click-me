import base64

from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.schemas import ProductAnalysis

_client = AsyncOpenAI(timeout=120.0)

_STRATEGY_DESCRIPTIONS: dict[AdStrategy, str] = {
    AdStrategy.BENEFIT: "highlighting product benefits and value proposition",
    AdStrategy.PROBLEM_SOLVING: "showing how the product solves customer pain points",
    AdStrategy.SOCIAL_PROOF: "emphasizing trust, reviews, and social credibility",
    AdStrategy.EMOTIONAL: "evoking emotions and emotional connection with the brand",
    AdStrategy.FOMO: "creating urgency and FOMO with limited-time messaging",
}

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


@traceable(name="ImageGenerator", metadata={"pipeline": "generator"})
async def generate_image(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    size: AdSize = AdSize.SQUARE,
    brand_color: str | None = None,
    tone: str | None = None,
) -> bytes:
    color_line = (
        f"Brand color accent: {brand_color} — incorporate into highlights and secondary elements"
        if brand_color
        else "Color palette: modern, clean, professional"
    )
    tone_line = f"Tone and manner: {tone}" if tone else "Tone: clean, professional, trustworthy"
    core_values_line = (
        f"Core values: {', '.join(product_analysis.core_values)}\n"
        if product_analysis.core_values
        else ""
    )
    target_audience = product_analysis.target_audience or "general audience"
    product_visual_context = _build_product_visual_context(product_analysis, brand_color)

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
        product_visual_context=product_visual_context,
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
