import io

from langsmith import traceable
from PIL import Image

from core.config import settings
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.pipeline import image_providers

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
        "Product-focused e-commerce photography: the product centered, large and hero. "
        "Clean, well-lit with soft even shadows, bright optimistic lighting, "
        "minimal uncluttered background that makes product details and quality pop."
    ),
    AdStrategy.PROBLEM_SOLVING: (
        "Lifestyle photography of a real, relatable everyday scene where the product "
        "naturally solves a small frustration. Contrast lighting shifting from dull to bright "
        "to suggest improvement and change. Natural, empathetic, true-to-life setting."
    ),
    AdStrategy.SOCIAL_PROOF: (
        "Authentic UGC-style photography that looks like a real Instagram post, not an ad. "
        "Casual hand-held feel, real-world context, genuine everyday use. "
        "Approachable and trustworthy, as if shared by a satisfied customer."
    ),
    AdStrategy.EMOTIONAL: (
        "Emotional lifestyle photography with generous negative space and breathing room. "
        "Natural light, warm tones, soft bokeh, shallow depth of field, cinematic premium mood. "
        "The product appears subtly within an aspirational, comforting atmosphere."
    ),
    AdStrategy.FOMO: (
        "Bold promotional photography for a flash-sale feel. Dramatic high-contrast lighting, "
        "vibrant punchy colors, dynamic eye-grabbing composition that creates urgency. "
        "High-conversion Meta promotion aesthetic. "
        "The packaged product is the HERO SUBJECT of the advertisement. "
        "The product must be the largest and most visually dominant object. "
        "Place the product in the center foreground. "
        "No person, hand, text, or decorative object may cover any part of the product. "
        "People are supporting elements only and must appear behind or beside the product. "
        "All subjects should direct attention toward the product. "
        "The advertisement should immediately communicate the product before any human subject."
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
# AI 이미지 모델이 텍스트를 이미지에 직접 렌더링할 때 각 템플릿의 레이아웃을 안내한다.
_TEXT_LAYOUT: dict[TemplateType, str] = {
    TemplateType.A: (
        "DESIGN LAYOUT — Bottom dark overlay:\n"
        "- Upper 55%: product photography, clean background, product centered\n"
        "- Bottom 45%: SOLID semi-opaque dark panel (rgba(0,0,0,0.75)), no gradient\n"
        "- Stack THREE elements top-to-bottom inside the dark panel, each in its own zone:\n"
        "  · ZONE 1 (top 30% of panel): HEADLINE — bold, compact size, white, horizontally centered\n"
        "  · ZONE 2 (middle 32% of panel): BODY — regular, smaller than headline, white/light gray, centered\n"
        "  · ZONE 3 (bottom 38% of panel): CTA BUTTON — rounded rectangle, brand color fill, "
        "white bold text, centered, 20px clearance from bottom edge\n"
        "MANDATORY RULES:\n"
        "1. ALL THREE elements must be 100% visible within the dark panel — no clipping.\n"
        "2. NO element may touch or cross the image boundary.\n"
        "3. CTA BUTTON is NOT optional. If it does not fit, make it and all text smaller.\n"
        "4. Do NOT use decorative fonts or large display sizes — keep text compact and readable."
    ),
    TemplateType.B: (
        "DESIGN LAYOUT — Top and bottom solid bands:\n"
        "- TOP BAND (top 22%): solid dark panel (rgba(0,0,0,0.85))\n"
        "  · HEADLINE: bold, compact size, white, horizontally centered in band\n"
        "- MIDDLE (22%–60%): product photography ONLY, no text\n"
        "- BOTTOM BAND (bottom 40%): solid dark panel\n"
        "  · SUB-ZONE A (top 55% of bottom band): BODY TEXT — regular, compact size, white, centered\n"
        "  · SUB-ZONE B (bottom 45% of bottom band): CTA BUTTON — rounded button, brand color, "
        "white bold text, centered, 20px clearance from bottom edge\n"
        "MANDATORY RULES:\n"
        "1. HEADLINE must be fully visible inside top band — no clipping.\n"
        "2. BODY TEXT must be fully visible inside sub-zone A — no clipping.\n"
        "3. CTA BUTTON must be fully visible inside sub-zone B — it is NOT optional.\n"
        "4. NO element may touch or cross the image boundary.\n"
        "5. If any element does not fit, reduce its font size until it fits."
    ),
    TemplateType.C: (
        "DESIGN LAYOUT — Left color panel + right product photo:\n"
        "- LEFT PANEL (left 46%): solid brand color background. "
        "All text elements must stay within this panel with minimum 20px padding from all panel edges.\n"
        "  · HEADLINE: bold, compact size, white, left-aligned (20px from left edge), "
        "placed in the upper section (top 10%–35% of image height). Max 2 lines\n"
        "  · BODY: regular, smaller than headline, white, left-aligned, "
        "placed below headline with at least 12px gap\n"
        "  · CTA BUTTON: white rounded rectangle, brand color text, left-aligned, "
        "placed in the lower section (70%–85% of image height). "
        "Button must have at least 20px clearance from bottom edge\n"
        "- GRADIENT ZONE (46%–53%): smooth transition from solid color to transparent\n"
        "- RIGHT SIDE (53%–100%): product photography, product clearly visible and centered\n"
        "MANDATORY RULES:\n"
        "1. ALL THREE elements must be 100% visible inside the left panel.\n"
        "2. Elements must not overlap each other — maintain clear vertical spacing.\n"
        "3. NO element may touch or cross any image boundary.\n"
        "4. CTA BUTTON is NOT optional — it must always appear."
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

# ── [컴포즈 모드] 텍스트 배치 가이드 (인페인팅) ───────────────────────────────
# 상품은 이미 캔버스에 배치되어 잠겨 있다. 텍스트/배경을 상품과 겹치지 않게 배치하도록 안내한다.
_TEMPLATE_SAFE_ZONES_COMPOSE: dict[TemplateType, str] = {
    TemplateType.A: (
        "LAYOUT: The locked product sits in the upper area. "
        "Build the background around it and keep the bottom 38% suitable for a text overlay — "
        "keep that zone visually simple and free of badges, stamps, watermarks, or any text-like graphic."
    ),
    TemplateType.B: (
        "LAYOUT: The locked product sits in the middle area. "
        "Keep the top 17% and bottom 24% suitable for text banners — "
        "keep those zones visually simple and free of badges, stamps, watermarks, or any text-like graphic."
    ),
    TemplateType.C: (
        "LAYOUT: The locked product sits on the RIGHT side. "
        "Keep the left 46% suitable for a text panel — "
        "keep that zone visually simple and free of badges, stamps, watermarks, or any text-like graphic."
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
If the image already has any text, headline, CTA button, badge, or other typography \
baked into it, REMOVE it completely and naturally reconstruct that area (e.g. extend the \
background or photography) — a new text overlay will be added separately afterward, \
so the output must contain ZERO text.

Product: {product_name}
Core values: {core_values}
Target audience: {target_audience}

Strategy to reinforce: {strategy_desc}
Visual style guidance: {style}
Photography style: {photo_style}
{color_line}
{tone_line}

Improvement direction (apply these changes to the existing image):
{improvement_context}

{safe_zone}

Requirements:
- PRESERVE the original product, composition, and layout as much as possible
- Make only the changes specified in the improvement direction above
- REMOVE any existing text, letters, words, numbers, or typography found in the source image
- STRICTLY NO text, letters, words, numbers, or typography in the output
- Keep the product clearly recognizable
- Adjust lighting, color, or mood only as needed by the improvement direction"""


# ── [텍스트 포함 생성 모드] 프롬프트 ────────────────────────────────────────
# AI 이미지 모델이 헤드라인·본문·CTA를 직접 렌더링할 때 사용.
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
- Headline: bold weight, high contrast (white on dark background) — size must fit within its zone
- Body: regular weight, smaller than headline — size must fit within its zone
- CTA: bold, placed inside a clearly visible rounded button shape
- NEVER use a font size so large that text overflows its designated zone
- Text edges must be sharp and pixel-perfect — no blur, no hallucinated characters
- NEVER use a font size so large that text overflows its designated zone

Output requirements:
- Commercial advertising quality, modern and clean aesthetic for Meta/Instagram
- Product clearly visible and well-lit
- CRITICAL: ALL three text elements (HEADLINE, BODY, CTA BUTTON) must be COMPLETELY visible within the image — zero clipping or cutoff allowed under any circumstance"""

# ── [컴포즈 모드] 프롬프트 (마스크 인페인팅) ─────────────────────────────────
# 실제 상품 PNG를 캔버스에 미리 배치하고 마스크로 잠근 뒤 Edit API에 넘긴다.
# AI는 잠긴 상품은 그대로 두고, 그 주위 배경·조명·그림자(+텍스트)를 한 패스로 생성한다.
# → 상품 픽셀은 보존되면서 장면에 자연스럽게 통합된다.
_COMPOSE_PROMPT_TEMPLATE = """\
This image already contains a REAL product photo that is LOCKED and must not change.
DO NOT alter, move, redraw, recolor, or stylize the product in any way.
If the product has its own text, logo, or label printed on it, PRESERVE it exactly as pixels —
never redraw, re-spell, or hallucinate any character on the product.
Your task: generate a professional {platform} advertisement BACKGROUND around the locked product.

Visual style: {style}
Photography style: {photo_style}
Strategy: {strategy_desc}

Product: {product_name}
{core_values_line}Target audience: {target_audience}
{color_line}
{tone_line}

Background direction:
{product_visual_context}

{safe_zone}

Requirements:
- Keep the locked product EXACTLY as-is — zero modification to its pixels, including any text on it
- Build a cohesive background that matches the product's lighting and perspective
- Add a natural, soft contact shadow under the product so it sits naturally in the scene
- STRICTLY NO new text, letters, words, numbers, or typography anywhere in the background
- No logos, watermarks, URLs, or QR codes
- Clean, modern aesthetic suitable for Meta/Instagram feed"""

_COMPOSE_PROMPT_TEMPLATE_WITH_TEXT = """\
This image already contains a REAL product photo that is LOCKED and must not change.
DO NOT alter, move, redraw, recolor, or stylize the product in any way.
Your task: generate a professional Korean {platform} advertisement around the locked product —
the background scene AND the Korean ad text overlay.

Visual style: {style}
Photography style: {photo_style}
Strategy: {strategy_desc}

Product: {product_name}
{core_values_line}Target audience: {target_audience}
{color_line}
{tone_line}

Background direction:
{product_visual_context}

{text_layout}

KOREAN TEXT — render EXACTLY as written, character by character (zero tolerance for typos):
  Headline : "{headline}"
  Body     : "{body}"
  CTA      : "{cta}"

Typography rules:
- All text must be in Korean (한국어) — every character must be a valid, correctly spelled Korean word
- Headline: bold weight, high contrast (white on dark background) — size must fit within its zone
- Body: regular weight, smaller than headline — size must fit within its zone
- CTA: bold, placed inside a clearly visible rounded button shape
- NEVER use a font size so large that text overflows its designated zone

Output requirements:
- Keep the locked product EXACTLY as-is — zero modification to its pixels
- Add a natural soft contact shadow so the product sits naturally in the scene
- Place text only in its designated zones — never overlap the product
- Commercial advertising quality, modern and clean aesthetic for Meta/Instagram
- CRITICAL: ALL three text elements (HEADLINE, BODY, CTA BUTTON) must be COMPLETELY visible — zero clipping"""


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
- Headline: bold, high contrast — size must fit within its designated zone
- Body: regular, smaller than headline — size must fit within its designated zone
- CTA: bold, rounded button shape, clearly clickable
- NEVER use a font size so large that text overflows its designated zone

Requirements:
- PRESERVE original product placement and visual identity
- Apply improvement direction changes
- Add text zones as specified in the layout above
- Keep product clearly recognizable
- CRITICAL: ALL three text elements (HEADLINE, BODY, CTA BUTTON) must be COMPLETELY visible within the image — zero clipping or cutoff allowed"""


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
# image_providers 디스패처를 통해 이미지 bytes를 반환한다.
# ─────────────────────────────────────────────────────────────────────────────
# 개선 모드(strategy=None)에서 쓰는 전략-독립 일반 문구 — CREATE 5전략 톤에 얽매이지 않고
# 시뮬레이션 피드백(improvement_context)만으로 방향을 결정하게 한다.
_IMPROVE_STRATEGY_DESC = "improving overall ad appeal and conversion based on feedback"
_IMPROVE_PHOTO_STYLE = (
    "Clean, professional commercial photography with balanced lighting and natural composition."
)


def _strategy_desc(strategy: AdStrategy | None) -> str:
    return _STRATEGY_DESCRIPTIONS[strategy] if strategy is not None else _IMPROVE_STRATEGY_DESC


def _strategy_photo_style(strategy: AdStrategy | None) -> str:
    return _STRATEGY_PHOTO_STYLE[strategy] if strategy is not None else _IMPROVE_PHOTO_STYLE


@traceable(
    name="generator:generate_image", metadata={"pipeline": "generator", "prompt_version": "v1.0"}
)
async def generate_image(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy | None,
    template: TemplateType | None,
    size: AdSize = AdSize.SQUARE,
    brand_color: str | None = None,
    tone: str | None = None,
    original_image_bytes: bytes | None = None,
    product_cutout_bytes: bytes | None = None,
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
    # 텍스트는 이미지 생성 후 text_overlay(PIL)로 렌더한다 — AI는 글자를 그리지 않는다
    # (확산모델 텍스트 잘림·오탈자 방지). 모든 경로(생성/컴포즈/개선)가 텍스트 없는 프롬프트를 탄다.
    has_text = False
    core_values_line = (
        f"Core values: {', '.join(product_analysis.core_values)}\n"
        if product_analysis.core_values
        else ""
    )

    # ── [컴포즈 모드] 상품 픽셀 보존 + 주변 배경 생성 ────────────────────────────
    # 마스크 인페인팅으로 상품 영역 잠금 후 배경 생성 (provider는 settings.inpaint_provider).
    # 개선 모드도 CREATE와 동일한 실제 템플릿(A/B/C)·세이프존을 쓰고, improvement_context만
    # product_visual_context에 병합해 반영한다(자유 레이아웃 아님 — PIL 텍스트 오버레이 위치와
    # 어긋나지 않도록 구도를 템플릿에 고정).
    if product_cutout_bytes is not None:
        # template=None(예상 밖 호출 등 방어적 폴백)이면 A로 — 실사용 경로에서는 항상 실값.
        effective_compose_template = template if template is not None else TemplateType.A
        target_audience = product_analysis.target_audience or "general audience"
        product_visual_context = _build_product_visual_context(product_analysis, brand_color)
        if improvement_context:
            product_visual_context += (
                f"\n\nImprovement direction (apply to visual):\n{improvement_context}"
            )

        if has_text:
            prompt = _COMPOSE_PROMPT_TEMPLATE_WITH_TEXT.format(
                platform="Meta/Instagram",
                style=_TEMPLATE_STYLE[effective_compose_template],
                photo_style=_strategy_photo_style(strategy),
                strategy_desc=_strategy_desc(strategy),
                product_name=product_analysis.product_name,
                core_values_line=core_values_line,
                target_audience=target_audience,
                color_line=color_line,
                tone_line=tone_line,
                product_visual_context=product_visual_context,
                text_layout=_TEXT_LAYOUT[effective_compose_template],
                headline=headline,
                body=body,
                cta=cta,
            )
        else:
            prompt = _COMPOSE_PROMPT_TEMPLATE.format(
                platform="Meta/Instagram",
                style=_TEMPLATE_STYLE[effective_compose_template],
                photo_style=_strategy_photo_style(strategy),
                strategy_desc=_strategy_desc(strategy),
                product_name=product_analysis.product_name,
                core_values_line=core_values_line,
                target_audience=target_audience,
                color_line=color_line,
                tone_line=tone_line,
                product_visual_context=product_visual_context,
                safe_zone=_TEMPLATE_SAFE_ZONES_COMPOSE[effective_compose_template],
            )

        base_png, mask_png = _build_inpaint_base_and_mask(
            product_cutout_bytes, effective_compose_template, size
        )
        return await image_providers.edit_with_mask(
            base_png,
            mask_png,
            prompt,
            size,
            provider=settings.inpaint_provider,
            model=settings.inpaint_model,
        )

    # ── [개선 모드] Edit API ───────────────────────────────────────────────────
    if original_image_bytes is not None:
        # template=None(개선 모드, 누끼 없이 원본 Edit)이면 A 레이아웃 문구로 폴백 —
        # _TEMPLATE_STYLE/_TEMPLATE_SAFE_ZONES_EDIT/_TEXT_LAYOUT은 None 키가 없어 KeyError 방지.
        effective_edit_template = template if template is not None else TemplateType.A
        core_values_str = (
            ", ".join(product_analysis.core_values) if product_analysis.core_values else "N/A"
        )
        target_audience = product_analysis.target_audience or "general audience"

        if has_text:
            prompt = _EDIT_PROMPT_TEMPLATE_WITH_TEXT.format(
                product_name=product_analysis.product_name,
                core_values=core_values_str,
                target_audience=target_audience,
                strategy_desc=_strategy_desc(strategy),
                color_line=color_line,
                tone_line=tone_line,
                improvement_context=improvement_context or "전반적인 광고 품질을 개선하세요.",
                text_layout=_TEXT_LAYOUT[effective_edit_template],
                headline=headline,
                body=body,
                cta=cta,
            )
        else:
            prompt = _EDIT_PROMPT_TEMPLATE.format(
                product_name=product_analysis.product_name,
                core_values=core_values_str,
                target_audience=target_audience,
                strategy_desc=_strategy_desc(strategy),
                style=_TEMPLATE_STYLE[effective_edit_template],
                photo_style=_strategy_photo_style(strategy),
                color_line=color_line,
                tone_line=tone_line,
                improvement_context=improvement_context or "전반적인 광고 품질을 개선하세요.",
                safe_zone=_TEMPLATE_SAFE_ZONES_EDIT[effective_edit_template],
            )

        return await image_providers.edit(
            original_image_bytes,
            prompt,
            size,
            provider=settings.generator_image_edit_provider,
            model=settings.generator_image_edit_model,
        )

    # ── [생성 모드] Generate API ──────────────────────────────────────────────
    # 개선 모드에서 누끼 없이 도달한 경우(product_cutout_s3_key 미제공 등) TemplateType.A 폴백
    effective_template = template if template is not None else TemplateType.A
    target_audience = product_analysis.target_audience or "general audience"
    product_visual_context = _build_product_visual_context(product_analysis, brand_color)

    if has_text:
        prompt = _PROMPT_TEMPLATE_WITH_TEXT.format(
            platform="Meta/Instagram",
            style=_TEMPLATE_STYLE[effective_template],
            photo_style=_strategy_photo_style(strategy),
            strategy_desc=_strategy_desc(strategy),
            product_name=product_analysis.product_name,
            core_values_line=core_values_line,
            target_audience=target_audience,
            color_line=color_line,
            tone_line=tone_line,
            product_visual_context=product_visual_context,
            text_layout=_TEXT_LAYOUT[effective_template],
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
            style=_TEMPLATE_STYLE[effective_template],
            photo_style=_strategy_photo_style(strategy),
            strategy_desc=_strategy_desc(strategy),
            product_name=product_analysis.product_name,
            core_values_line=core_values_line,
            target_audience=target_audience,
            color_line=color_line,
            tone_line=tone_line,
            product_visual_context=product_visual_context + improvement_line,
            safe_zone=_TEMPLATE_SAFE_ZONES[effective_template],
        )

    return await image_providers.generate(
        prompt,
        size,
        provider=settings.generator_image_provider,
        model=settings.generator_image_model,
        quality=settings.generator_image_quality,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 상품 누끼 (배경 제거) — gpt-image-1 edit + transparent background
# 사용자가 올린 상품 이미지에서 배경을 제거하고 알파 채널 PNG bytes를 반환한다.
# AI 추출이라 픽셀이 완벽히 동일하진 않으나, 전체 재생성 대비 원본에 훨씬 가깝다.
# ─────────────────────────────────────────────────────────────────────────────


@traceable(
    name="generator:remove_background",
    metadata={"pipeline": "generator", "step": "background_removal"},
)
async def remove_product_background(product_image_bytes: bytes) -> bytes:
    """상품 이미지의 배경을 제거하고 투명 PNG bytes를 반환한다."""
    return await image_providers.remove_background(
        product_image_bytes,
        provider=settings.cutout_provider,
        model=settings.cutout_model,
        quality=settings.cutout_quality,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 인페인팅용 베이스 캔버스 + 마스크 생성 (PIL 기반)
# 누끼한 상품을 템플릿별 영역에 배치한 베이스 이미지와, 상품 실루엣만 잠그는 마스크를 만든다.
# OpenAI 마스크 규약: 투명(alpha=0) 영역이 "수정될 곳" → 상품은 불투명(보존), 배경은 투명(생성).
# ─────────────────────────────────────────────────────────────────────────────

# 템플릿별 상품 배치 박스 — (x0, y0, x1, y1), 광고 가로/세로 대비 비율.
# 상품은 이 박스 안에 비율 유지로 들어가며 박스 중앙에 정렬된다.
_COMPOSE_PRODUCT_BOXES: dict[TemplateType, tuple[float, float, float, float]] = {
    TemplateType.A: (0.14, 0.06, 0.86, 0.52),  # 상단 영역(텍스트는 하단)
    TemplateType.B: (0.16, 0.20, 0.84, 0.74),  # 중앙 영역(텍스트는 상·하 밴드)
    TemplateType.C: (0.52, 0.16, 0.96, 0.84),  # 우측 영역(텍스트는 좌측 패널)
}
# 개선 모드 — template=None일 때 사용하는 중앙 상단 배치 박스(AI가 배경 구도 자유 결정)
_IMPROVE_PRODUCT_BOX: tuple[float, float, float, float] = (0.10, 0.06, 0.90, 0.72)

# 박스 대비 상품이 차지할 최대 비율(여백 확보).
_PRODUCT_FILL = 0.92


def _place_product(
    product: Image.Image, w: int, h: int, template: TemplateType | None, product_fill: float
) -> tuple[Image.Image, int, int]:
    """상품을 템플릿 박스에 비율 유지로 리사이즈하고 배치 좌표를 계산한다."""
    x0, y0, x1, y1 = (
        _COMPOSE_PRODUCT_BOXES[template] if template is not None else _IMPROVE_PRODUCT_BOX
    )
    box_w = max(1, int(w * (x1 - x0) * _PRODUCT_FILL))
    box_h = max(1, int(h * (y1 - y0) * _PRODUCT_FILL))
    target = max(1, int(min(w, h) * product_fill))  # 전략 비중 캡
    scale = min(
        box_w / product.width,
        box_h / product.height,
        target / max(product.width, product.height),
    )
    new_w = max(1, int(product.width * scale))
    new_h = max(1, int(product.height * scale))
    product = product.resize((new_w, new_h), Image.LANCZOS)
    cx = int(w * (x0 + x1) / 2)
    cy = int(h * (y0 + y1) / 2)
    return product, cx - new_w // 2, cy - new_h // 2


def _build_inpaint_base_and_mask(
    product_cutout_bytes: bytes, template: TemplateType | None, size: AdSize
) -> tuple[bytes, bytes]:
    """누끼 상품을 배치한 베이스 PNG와, 상품 실루엣만 보존하는 마스크 PNG를 만든다."""
    w, h = (int(v) for v in size.value.split("x"))
    product = Image.open(io.BytesIO(product_cutout_bytes)).convert("RGBA")
    product, x, y = _place_product(product, w, h, template, _PRODUCT_FILL)

    # 베이스: 중립 회색 위에 상품 배치 (배경 영역은 어차피 재생성됨)
    base = Image.new("RGBA", (w, h), (245, 245, 245, 255))
    base.paste(product, (x, y), product)

    # 마스크: 전체 투명(수정 대상) + 상품 실루엣만 불투명(보존)
    mask = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    keep = Image.new("RGBA", product.size, (255, 255, 255, 255))
    mask.paste(keep, (x, y), product)  # 상품 알파를 따라 불투명 영역 형성

    base_buf, mask_buf = io.BytesIO(), io.BytesIO()
    base.save(base_buf, format="PNG")
    mask.save(mask_buf, format="PNG")
    return base_buf.getvalue(), mask_buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 로고 합성 (PIL 기반)
# ─────────────────────────────────────────────────────────────────────────────


def _composite_logo_pil(
    logo: Image.Image,
    ad: Image.Image,
    template: TemplateType,
    margin: int = 16,
) -> None:
    """로고를 광고 이미지에 in-place 합성한다. 템플릿별 위치 규칙 적용."""
    if logo.mode != "RGBA":
        logo = logo.convert("RGBA")

    if template == TemplateType.A:
        # 상단 좌측 — 제품 상단(55%) 영역에 작게 배치
        logo_w = max(1, int(ad.width * 0.12))
        logo_h = max(1, int(logo.height * logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        x, y = margin, margin
    elif template == TemplateType.B:
        # 상단 밴드(top 22%) 내 좌측 수직 중앙
        band_h = int(ad.height * 0.22)
        logo_w = max(1, int(ad.width * 0.10))
        logo_h = max(1, int(logo.height * logo_w / logo.width))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        x = margin
        y = max(margin, (band_h - logo_h) // 2)
    else:  # C
        # 좌측 패널(left 46%) 상단 좌측 — 하단 CTA와 겹치지 않도록 상단 배치
        max_logo_h = int(ad.height * 0.08)
        logo_w = max(1, int(ad.width * 0.12))
        logo_h = max(1, int(logo.height * logo_w / logo.width))
        if logo_h > max_logo_h:
            logo_h = max_logo_h
            logo_w = max(1, int(logo.width * logo_h / logo.height))
        logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
        x = margin
        y = margin

    ad.paste(logo, (x, y), logo)


def composite_logo(image_bytes: bytes, logo_bytes: bytes, template: TemplateType | None) -> bytes:
    """로고를 광고 이미지에 합성하여 PNG bytes로 반환한다.

    template=None(개선 모드)이면 Template A와 같이 좌상단에 배치한다.
    """
    ad = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    _composite_logo_pil(logo, ad, template if template is not None else TemplateType.A)
    buf = io.BytesIO()
    ad.save(buf, format="PNG")
    return buf.getvalue()
