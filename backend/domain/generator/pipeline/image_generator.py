import base64

from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.schemas import AdCopy, ProductAnalysis
from domain.generator.pipeline.template_selector import describe_template

_client = AsyncOpenAI(timeout=120.0)

_STRATEGY_DESCRIPTIONS: dict[AdStrategy, str] = {
    AdStrategy.BENEFIT: "highlighting product benefits and value proposition",
    AdStrategy.PROBLEM_SOLVING: "showing how the product solves customer pain points",
    AdStrategy.SOCIAL_PROOF: "emphasizing trust, reviews, and social credibility",
    AdStrategy.EMOTIONAL: "evoking emotions and emotional connection with the brand",
    AdStrategy.URGENCY: "creating urgency and FOMO with limited-time messaging",
}

_TEMPLATE_LAYOUT: dict[TemplateType, str] = {
    TemplateType.A: (
        "Product-focused layout: large headline text at top, "
        "product image prominently centered, CTA button at bottom"
    ),
    TemplateType.B: (
        "Promotional/event layout: bold large promotional text dominant, "
        "small product image, oversized CTA button"
    ),
    TemplateType.C: (
        "Brand-focused layout: brand logo and colors prominent, "
        "emotional lifestyle imagery, elegant typography"
    ),
}

_PROMPT_TEMPLATE = """\
Create a professional {platform} advertisement image.

Layout: {layout}
Strategy: {strategy_desc}

Ad copy to include:
- Headline: "{headline}"
- Body: "{body}"
- CTA: "{cta}"

Product: {product_name}
{color_line}
{tone_line}

Requirements:
- High-quality, commercial advertising style
- Korean text rendered clearly and legibly
- Clean, modern aesthetic suitable for Meta/Instagram feed
- Do not include any URLs, website addresses, or QR codes
- Photo-realistic or high-quality illustration style"""


@traceable(name="ImageGenerator", metadata={"pipeline": "generator"})
async def generate_image(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
    ad_copy: AdCopy,
    size: AdSize = AdSize.SQUARE,
    brand_color: str | None = None,
    tone: str | None = None,
) -> bytes:
    color_line = f"Brand color: {brand_color}" if brand_color else "Color palette: modern, clean, professional"
    tone_line = f"Tone and manner: {tone}" if tone else "Tone: clean, professional, trustworthy"

    prompt = _PROMPT_TEMPLATE.format(
        platform="Meta/Instagram",
        layout=_TEMPLATE_LAYOUT[template],
        strategy_desc=_STRATEGY_DESCRIPTIONS[strategy],
        headline=ad_copy.headline,
        body=ad_copy.body,
        cta=ad_copy.cta,
        product_name=product_analysis.product_name,
        color_line=color_line,
        tone_line=tone_line,
    )

    response = await _client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        n=1,
        size=size.value,
        quality="high",
    )

    return base64.b64decode(response.data[0].b64_json)
