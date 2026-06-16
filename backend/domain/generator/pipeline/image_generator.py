import base64
import io

from langsmith import traceable
from openai import AsyncOpenAI

from core.config import settings
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import ProductAnalysis

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

# ── 텍스트 포함 생성 모드: 템플릿별 레이아웃 + 텍스트 배치 지시 ───────────────
# gpt-image-2가 텍스트를 이미지에 직접 렌더링할 때 각 템플릿의 레이아웃을 안내한다.
_TEXT_LAYOUT: dict[TemplateType, str] = {
    TemplateType.A: (
        "DESIGN LAYOUT — Bottom gradient overlay:\n"
        "- Upper 62%: product photography, clean background, product centered\n"
        "- Bottom 38%: dark-to-transparent gradient overlay (part of the composition)\n"
        "- Within the overlay, place text top-to-bottom:\n"
        "  · HEADLINE: bold, ~28pt, white, horizontally centered, at ~65% from top\n"
        "  · BODY: regular, ~16pt, white/light gray, centered, just below headline\n"
        "  · CTA BUTTON: rounded rectangle, brand color fill, white bold text, "
        "centered, near very bottom"
    ),
    TemplateType.B: (
        "DESIGN LAYOUT — Top and bottom solid bands:\n"
        "- TOP BAND (top 17%): solid dark panel\n"
        "  · HEADLINE: bold, ~22pt, white, horizontally centered in band\n"
        "- MIDDLE (17%–76%): product photography only, no text\n"
        "- BOTTOM BAND (bottom 24%): solid dark panel\n"
        "  · BODY: regular, ~14pt, white, centered in upper portion of band\n"
        "  · CTA BUTTON: rounded button, brand color, white bold text, "
        "centered in lower portion of band"
    ),
    TemplateType.C: (
        "DESIGN LAYOUT — Left color panel + right product photo:\n"
        "- LEFT PANEL (left 46%): solid brand color background\n"
        "  · HEADLINE: bold, ~24pt, white, left-aligned with padding, upper third\n"
        "  · BODY: regular, ~14pt, white, left-aligned, below headline\n"
        "  · CTA BUTTON: white rounded rectangle, brand color text, "
        "left-aligned, near bottom of panel\n"
        "- GRADIENT ZONE (46%–53%): smooth transition from solid color to transparent\n"
        "- RIGHT SIDE (53%–100%): product photography, product clearly visible and centered"
    ),
}

# ── [생성 모드] Safe Zone ─────────────────────────────────────────────────────
# 텍스트 오버레이가 가려질 영역을 AI에게 알려주는 Safe Zone 지시문.
# 각 템플릿은 텍스트 배너 위치가 다르므로, 제품이 가리지 않도록 구도를 강하게 유도한다.
# 생성 모드에서 사용 — 처음부터 올바른 구도로 이미지를 만들어야 하므로 강제 배치 지시.
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
        "COMPOSITION RULE: The left 46% of the frame is a solid color text panel — keep it empty. "
        "The area from 46% to 53% has a gradient overlay fading to transparent. "
        "Place the product clearly in the RIGHT 47% of the frame "
        "(center the product at approximately 75-80% from the left edge). "
        "No important visual elements in the left 53% of the frame."
    ),
}

# ── [개선 모드] Safe Zone ─────────────────────────────────────────────────────
# 원본 이미지 구도를 최대한 유지하면서 텍스트 오버레이 영역만 참고용으로 알려준다.
# 개선 모드에서 사용 — 강제 배치 지시 대신 "가능하면 비워달라"는 소프트 힌트로 처리.
# 생성 모드(_TEMPLATE_SAFE_ZONES)처럼 구도를 강제하면 원본 레이아웃이 크게 훼손된다.
_TEMPLATE_SAFE_ZONES_EDIT: dict[TemplateType, str] = {
    TemplateType.A: (
        "LAYOUT NOTE: Text overlays will cover the bottom 38% of the frame. "
        "If possible, avoid placing critical product details in that area, "
        "but do NOT restructure the original composition."
    ),
    TemplateType.B: (
        "LAYOUT NOTE: Text banners will cover the top 17% and bottom 24% of the frame. "
        "If possible, keep those areas relatively uncluttered, "
        "but do NOT restructure the original composition."
    ),
    TemplateType.C: (
        "LAYOUT NOTE: A text panel will cover the left 46% of the frame. "
        "If possible, keep the left side lighter or less detailed, "
        "but do NOT restructure the original composition."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# 이미지 생성 프롬프트 템플릿
# 위에서 정의한 스타일·전략 값들이 format()으로 조합되어 최종 프롬프트를 구성한다.
# ─────────────────────────────────────────────────────────────────────────────

# ── [생성 모드] 프롬프트 ──────────────────────────────────────────────────────
# 제품 정보와 전략을 바탕으로 처음부터 새 광고 이미지를 생성할 때 사용.
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

# ── [개선 모드] 프롬프트 ──────────────────────────────────────────────────────
# 원본 이미지를 Edit API로 수정할 때 사용 (직접 수정 / 시뮬레이션 기반 모두 해당).
# 생성 모드 프롬프트와 달리 제품·구도 보존 지시를 최상단에 강하게 명시하고,
# 제품명·핵심 가치·타겟을 포함해 모델이 무엇을 보존해야 하는지 파악하도록 한다.
_EDIT_PROMPT_TEMPLATE = """\
IMPORTANT: This is an EXISTING advertisement image. \
Your PRIMARY goal is to PRESERVE the original composition, product placement, \
and visual identity. Apply only the targeted improvements described below.

Product: {product_name}
Core values: {core_values}
Target audience: {target_audience}

Strategy to reinforce: {strategy_desc}
Visual style guidance: {style}
{color_line}
{tone_line}

Improvement direction (apply these changes to the existing image):
{improvement_context}

{safe_zone}

Requirements:
- PRESERVE the original product, composition, and layout as much as possible
- Make only the changes specified in the improvement direction above
- STRICTLY NO text, letters, words, numbers, or typography
- Keep the product clearly recognizable
- Adjust lighting, color, or mood only as needed by the improvement direction"""


# ── [텍스트 포함 생성 모드] 프롬프트 ────────────────────────────────────────
# gpt-image-2가 헤드라인·본문·CTA를 이미지에 직접 렌더링할 때 사용.
_PROMPT_TEMPLATE_WITH_TEXT = """\
Create a professional Korean {platform} advertisement image with integrated Korean text.

Visual style: {style}
Photography style: {photo_style}
Strategy: {strategy_desc}

Product: {product_name}
{core_values_line}Target audience: {target_audience}
{color_line}
{tone_line}

Product visual direction:
{product_visual_context}

{text_layout}

KOREAN TEXT — render EXACTLY as written, character by character (zero tolerance for typos):
  Headline : "{headline}"
  Body     : "{body}"
  CTA      : "{cta}"

Typography rules:
- All text must be in Korean (한국어) — every character must be a valid, correctly spelled Korean word
- Headline: bold weight, large size, high contrast (white or bright on dark background)
- Body: regular weight, smaller size, clean and readable
- CTA: bold, placed inside a clearly visible rounded button shape
- Text edges must be sharp and pixel-perfect — no blur, no hallucinated characters

Output requirements:
- Commercial advertising quality, modern and clean aesthetic for Meta/Instagram
- Product clearly visible and well-lit
- Text is fully integrated into the composition, not an afterthought"""

# ── [텍스트 포함 개선 모드] 프롬프트 ────────────────────────────────────────
# 원본 이미지를 Edit API로 수정하면서 텍스트도 함께 삽입할 때 사용.
_EDIT_PROMPT_TEMPLATE_WITH_TEXT = """\
IMPORTANT: Modify this advertisement image. \
Preserve the original product and composition, apply the specified improvements, \
and add the Korean text overlay as described below.

Product: {product_name}
Core values: {core_values}
Target audience: {target_audience}
Strategy: {strategy_desc}
{color_line}
{tone_line}

Improvement direction:
{improvement_context}

{text_layout}

KOREAN TEXT — render EXACTLY as written, character by character (zero tolerance for typos):
  Headline : "{headline}"
  Body     : "{body}"
  CTA      : "{cta}"

Typography rules:
- All text in Korean (한국어) — must be valid, correctly spelled Korean
- Headline: bold, large, high contrast
- Body: regular, smaller, readable
- CTA: bold, rounded button shape, clearly clickable

Requirements:
- PRESERVE original product placement and visual identity
- Apply improvement direction changes
- Add text zones as specified in the layout above
- Keep product clearly recognizable"""


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
    headline: str | None = None,
    body: str | None = None,
    cta: str | None = None,
) -> bytes:
    color_line = (
        f"Brand color accent: {brand_color} — incorporate into highlights and secondary elements"
        if brand_color
        else "Color palette: modern, clean, professional"
    )
    tone_line = f"Tone and manner: {tone}" if tone else "Tone: clean, professional, trustworthy"
    has_text = bool(headline and body and cta)

    # ── [개선 모드] Edit API ───────────────────────────────────────────────────
    if original_image_bytes is not None:
        core_values_str = (
            ", ".join(product_analysis.core_values) if product_analysis.core_values else "N/A"
        )
        target_audience = product_analysis.target_audience or "general audience"

        if has_text:
            prompt = _EDIT_PROMPT_TEMPLATE_WITH_TEXT.format(
                product_name=product_analysis.product_name,
                core_values=core_values_str,
                target_audience=target_audience,
                strategy_desc=_STRATEGY_DESCRIPTIONS[strategy],
                color_line=color_line,
                tone_line=tone_line,
                improvement_context=improvement_context or "전반적인 광고 품질을 개선하세요.",
                text_layout=_TEXT_LAYOUT[template],
                headline=headline,
                body=body,
                cta=cta,
            )
        else:
            prompt = _EDIT_PROMPT_TEMPLATE.format(
                product_name=product_analysis.product_name,
                core_values=core_values_str,
                target_audience=target_audience,
                strategy_desc=_STRATEGY_DESCRIPTIONS[strategy],
                style=_TEMPLATE_STYLE[template],
                color_line=color_line,
                tone_line=tone_line,
                improvement_context=improvement_context or "전반적인 광고 품질을 개선하세요.",
                safe_zone=_TEMPLATE_SAFE_ZONES_EDIT[template],
            )

        image_file = io.BytesIO(original_image_bytes)
        image_file.name = "original.png"
        response = await _client.images.edit(
            model=settings.generator_image_model,
            image=image_file,
            prompt=prompt,
            n=1,
            size=size.value,
        )
        return base64.b64decode(response.data[0].b64_json)

    # ── [생성 모드] Generate API ──────────────────────────────────────────────
    core_values_line = (
        f"Core values: {', '.join(product_analysis.core_values)}\n"
        if product_analysis.core_values
        else ""
    )
    target_audience = product_analysis.target_audience or "general audience"
    product_visual_context = _build_product_visual_context(product_analysis, brand_color)

    if has_text:
        prompt = _PROMPT_TEMPLATE_WITH_TEXT.format(
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
            text_layout=_TEXT_LAYOUT[template],
            headline=headline,
            body=body,
            cta=cta,
        )
    else:
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
        model=settings.generator_image_model,
        prompt=prompt,
        n=1,
        size=size.value,
        quality=settings.generator_image_quality,
    )

    return base64.b64decode(response.data[0].b64_json)
