import base64
import io
from typing import Any

from google import genai
from google.genai import types as genai_types
from langsmith import get_current_run_tree, traceable
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI
from PIL import Image

from core.config import settings
from domain.generator.contracts.enums import AdSize, AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.pipeline.style_profile import get_style

# wrap_openai로 감싸 이미지/Responses 호출의 토큰·비용 usage가 LangSmith에 기록되게 한다.
_openai_client = wrap_openai(AsyncOpenAI(timeout=settings.generator_image_timeout))

_GEMINI_NATIVE_ASPECT_RATIO: dict[AdSize, str] = {
    AdSize.SQUARE: "1:1",
    AdSize.LANDSCAPE: "3:2",
    AdSize.PORTRAIT: "2:3",
}

# Imagen은 "1:1"/"3:4"/"4:3"/"9:16"/"16:9"만 지원 — AdSize 비율에 가장 가까운 값으로 매핑
_IMAGEN_ASPECT_RATIO: dict[AdSize, str] = {
    AdSize.SQUARE: "1:1",
    AdSize.LANDSCAPE: "4:3",
    AdSize.PORTRAIT: "3:4",
}

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
        "High-conversion Meta promotion aesthetic."
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
        "Build the background around it and keep the bottom 38% suitable for a text overlay."
    ),
    TemplateType.B: (
        "LAYOUT: The locked product sits in the middle area. "
        "Keep the top 17% and bottom 24% suitable for text banners."
    ),
    TemplateType.C: (
        "LAYOUT: The locked product sits on the RIGHT side. "
        "Keep the left 46% suitable for a text panel."
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
# GPT Image API를 호출한 뒤 base64 디코딩된 이미지 bytes를 반환한다.
# ─────────────────────────────────────────────────────────────────────────────
@traceable(
    name="generator:generate_image", metadata={"pipeline": "generator", "prompt_version": "v1.0"}
)
async def generate_image(
    product_analysis: ProductAnalysis,
    strategy: AdStrategy,
    template: TemplateType,
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

    # ── [컴포즈 모드] 마스크 인페인팅 — 상품 잠금 + 주변 배경/텍스트 생성 ──────────
    if product_cutout_bytes is not None:
        target_audience = product_analysis.target_audience or "general audience"
        product_visual_context = _build_product_visual_context(product_analysis, brand_color)

        if has_text:
            prompt = _COMPOSE_PROMPT_TEMPLATE_WITH_TEXT.format(
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
            prompt = _COMPOSE_PROMPT_TEMPLATE.format(
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
                safe_zone=_TEMPLATE_SAFE_ZONES_COMPOSE[template],
            )

        base_png, mask_png = _build_inpaint_base_and_mask(
            product_cutout_bytes, template, size, get_style(strategy).product_fill
        )
        base_file = io.BytesIO(base_png)
        base_file.name = "base.png"
        mask_file = io.BytesIO(mask_png)
        mask_file.name = "mask.png"
        return await _edit_with_openai(base_file, prompt, size, mask_file=mask_file)

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
        return await _edit_with_openai(image_file, prompt, size)

    # ── [생성 모드] Generate API ──────────────────────────────────────────────
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

    provider = settings.generator_image_provider
    if provider == "openai":
        image_bytes = await _generate_with_openai(prompt, size)
    elif provider == "google_genai":
        image_bytes = await _generate_with_gemini(prompt, size)
    else:
        raise NotImplementedError(f"지원하지 않는 GENERATOR_IMAGE_PROVIDER: {provider!r}")

    return image_bytes


@traceable(name="image-model:openai", run_type="llm")
async def _generate_with_openai(prompt: str, size: AdSize) -> bytes:
    model = settings.generator_image_model
    quality = settings.generator_image_quality
    kwargs: dict = {"model": model, "prompt": prompt, "n": 1, "size": size.value}
    # gpt-image-1은 response_format 파라미터를 지원하지 않음 (항상 b64_json 반환)
    if not model.startswith("gpt-image"):
        kwargs["response_format"] = "b64_json"
        kwargs["quality"] = quality
    response = await _openai_client.images.generate(**kwargs)
    _record_openai_usage(response, model, size, quality)
    return base64.b64decode(response.data[0].b64_json)


@traceable(name="image-model:openai-edit", run_type="llm")
async def _edit_with_openai(
    image_file: io.BytesIO, prompt: str, size: AdSize, mask_file: io.BytesIO | None = None
) -> bytes:
    """OpenAI images.edit 호출(컴포즈·개선·누끼 공통) — 모델명 런으로 분리해 토큰·시간·비용을 기록한다."""
    model = settings.generator_image_edit_model
    kwargs: dict = {
        "model": model,
        "image": image_file,
        "prompt": prompt,
        "n": 1,
        "size": size.value,
    }
    if mask_file is not None:
        kwargs["mask"] = mask_file
    response = await _openai_client.images.edit(**kwargs)
    _record_openai_usage(response, model, size, settings.generator_image_quality)
    return base64.b64decode(response.data[0].b64_json)


# ─────────────────────────────────────────────────────────────────────────────
# 이미지 모델 단가표 — 모델/사이즈/품질 → USD/장
# 이미지 API는 토큰 기반이 아니라 LangSmith 자동 집계가 안 되므로 직접 계산해 주입한다.
# 가격 변경 시 이 테이블만 업데이트하면 된다. (공식 출처: platform.openai.com/docs/pricing)
# ─────────────────────────────────────────────────────────────────────────────
_IMAGE_COST_TABLE: dict[str, dict[str, float]] = {
    # OpenAI — images.generate / images.edit (per image)
    "gpt-image-1": {
        "1024x1024_low": 0.011,
        "1024x1024_medium": 0.042,
        "1024x1024_high": 0.167,
        "1536x1024_low": 0.016,
        "1536x1024_medium": 0.063,
        "1536x1024_high": 0.250,
        "1024x1536_low": 0.016,
        "1024x1536_medium": 0.063,
        "1024x1536_high": 0.250,
    },
    "gpt-image-2": {
        "1024x1024_low": 0.020,
        "1024x1024_medium": 0.040,
        "1024x1024_high": 0.080,
        "1536x1024_low": 0.030,
        "1536x1024_medium": 0.060,
        "1536x1024_high": 0.120,
        "1024x1536_low": 0.030,
        "1024x1536_medium": 0.060,
        "1024x1536_high": 0.120,
    },
    # Google — Gemini native (이미지 출력 토큰 기반, 장당 근사값)
    "gemini-2.0-flash-preview-image-generation": {"default": 0.039},
    "gemini-2.5-flash-preview-05-20": {"default": 0.039},
    # Google — Imagen (per image, google.com/pricing 기준)
    "imagen-3.0-generate-002": {"default": 0.040},
    "imagen-4.0-generate-preview-06-05": {"default": 0.040},
}


def _lookup_image_cost(model: str, size: AdSize, quality: str | None) -> float:
    """단가표에서 이미지 1장의 예상 비용(USD)을 조회한다. 미등록 모델은 0.0."""
    table = _IMAGE_COST_TABLE.get(model)
    if not table:
        return 0.0
    key = f"{size.value}_{quality}" if quality else "default"
    return table.get(key) or table.get("default") or 0.0


def _record_image_cost(model: str, provider: str, size: AdSize, quality: str | None) -> None:
    """이미지 생성 비용을 LangSmith 현재 run에 메타데이터로 주입한다.

    모든 provider(openai/google_genai)가 동일한 키(estimated_cost_usd)를 사용하므로
    모델을 바꿔도 LangSmith 대시보드에서 동일한 필드로 비교·집계할 수 있다.
    """
    run = get_current_run_tree()
    if run is None:
        return
    run.set(
        metadata={
            "ls_model_name": model,
            "ls_provider": provider,
            "image_size": size.value,
            "image_quality": quality or "default",
            "image_count": 1,
            "estimated_cost_usd": _lookup_image_cost(model, size, quality),
        }
    )


def _modality_breakdown(details: Any) -> dict[str, int]:
    """google-genai의 *_tokens_details(모달리티별 토큰 리스트)를 {text, image, ...} 합계 dict로 변환."""
    out: dict[str, int] = {}
    for item in details or []:
        modality = getattr(item, "modality", None)
        name = (getattr(modality, "name", None) or str(modality)).lower()
        out[name] = out.get(name, 0) + (getattr(item, "token_count", None) or 0)
    return out


def _record_openai_usage(resp: Any, model: str, size: AdSize, quality: str | None) -> None:
    """OpenAI 이미지 호출(images.generate/edit)의 토큰·모델명·비용을 현재 LangSmith run에 기록.

    Gemini의 _record_genai_usage와 동일 패턴 — 양쪽 provider가 같은 키(usage_metadata·estimated_cost_usd)로
    찍혀 모델을 바꿔도 대시보드에서 토큰·비용을 나란히 비교할 수 있다. 트레이싱 OFF면 무동작.
    """
    _record_image_cost(model, "openai", size, quality)
    run = get_current_run_tree()
    if run is None:
        return
    usage = getattr(resp, "usage", None)
    if usage is None:
        return
    payload: dict = {
        "input_tokens": getattr(usage, "input_tokens", None) or 0,
        "output_tokens": getattr(usage, "output_tokens", None) or 0,
        "total_tokens": getattr(usage, "total_tokens", None) or 0,
    }
    # 입력 토큰을 텍스트/이미지로 분해 (출력은 전부 생성 이미지) — 모델별 토큰 구성 비교용.
    details = getattr(usage, "input_tokens_details", None)
    if details is not None:
        payload["input_token_details"] = {
            "text": getattr(details, "text_tokens", None) or 0,
            "image": getattr(details, "image_tokens", None) or 0,
        }
    run.set(usage_metadata=payload)


def _record_genai_usage(resp: Any, model: str, size: AdSize) -> None:
    """google-genai 직접 호출(genai SDK)의 토큰·모델명을 현재 LangSmith run에 기록.

    LangChain/wrap_openai를 거치지 않는 호출은 토큰·비용이 자동 집계되지 않으므로 수동 주입한다
    (docs/langsmith-guide.md §7 표준 패턴). 이미지 전용 모델(Imagen 등)은 usage_metadata가 없을 수
    있어 모델명(ls_model_name)만이라도 남겨 비용 계산·필터가 가능하게 한다. 트레이싱 OFF면 무동작.
    """
    _record_image_cost(model, "google_genai", size, None)
    run = get_current_run_tree()
    if run is None:
        return
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        return
    payload: dict = {
        "input_tokens": getattr(um, "prompt_token_count", None) or 0,
        "output_tokens": getattr(um, "candidates_token_count", None) or 0,
        "total_tokens": getattr(um, "total_token_count", None) or 0,
    }
    # 모달리티(텍스트/이미지)별 분해 — 입력은 prompt_tokens_details, 출력은 candidates_tokens_details.
    prompt_details = _modality_breakdown(getattr(um, "prompt_tokens_details", None))
    if prompt_details:
        payload["input_token_details"] = prompt_details
    output_details = _modality_breakdown(getattr(um, "candidates_tokens_details", None))
    if output_details:
        payload["output_token_details"] = output_details
    run.set(usage_metadata=payload)


async def _generate_with_gemini(prompt: str, size: AdSize) -> bytes:
    model = settings.generator_image_model
    if model.startswith("imagen-"):
        return await _generate_with_imagen(model, prompt, size)
    return await _generate_with_gemini_native(model, prompt, size)


@traceable(name="image-model:gemini", run_type="llm")
async def _generate_with_gemini_native(model: str, prompt: str, size: AdSize) -> bytes:
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=genai_types.ImageConfig(aspect_ratio=_GEMINI_NATIVE_ASPECT_RATIO[size]),
        ),
    )
    _record_genai_usage(response, model, size)
    if not response.candidates:
        raise RuntimeError("Gemini 응답에 candidates가 없음")
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    raise RuntimeError("Gemini 응답에 이미지 데이터가 없음")


@traceable(name="image-model:imagen", run_type="llm")
async def _generate_with_imagen(model: str, prompt: str, size: AdSize) -> bytes:
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_images(
        model=model,
        prompt=prompt,
        config=genai_types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=_IMAGEN_ASPECT_RATIO[size],
        ),
    )
    _record_genai_usage(response, model, size)
    if not response.generated_images:
        raise RuntimeError("Imagen 응답에 이미지가 없음")
    return response.generated_images[0].image.image_bytes


# ─────────────────────────────────────────────────────────────────────────────
# 상품 누끼 (배경 제거) — gpt-image-2 edit + transparent background
# 사용자가 올린 상품 이미지에서 배경을 제거하고 알파 채널 PNG bytes를 반환한다.
# AI 추출이라 픽셀이 완벽히 동일하진 않으나, 전체 재생성 대비 원본에 훨씬 가깝다.
# ─────────────────────────────────────────────────────────────────────────────

_REMOVE_BG_PROMPT = (
    "Remove the background completely and keep ONLY the main product, "
    "fully preserving its exact shape, colors, text, and details. "
    "Output the product on a fully transparent background. "
    "Do not add, redraw, or stylize anything — keep the product identical to the input."
)


@traceable(name="image-model:remove-bg", run_type="llm")
async def remove_product_background(product_image_bytes: bytes) -> bytes:
    """상품 이미지의 배경을 제거하고 투명 PNG bytes를 반환한다."""
    image_file = io.BytesIO(product_image_bytes)
    image_file.name = "product.png"
    response = await _openai_client.images.edit(
        model=settings.generator_image_edit_model,
        image=image_file,
        prompt=_REMOVE_BG_PROMPT,
        n=1,
        background="transparent",
    )
    _record_openai_usage(
        response,
        settings.generator_image_edit_model,
        AdSize.SQUARE,
        settings.generator_image_quality,
    )
    return base64.b64decode(response.data[0].b64_json)


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

# 박스 대비 상품이 차지할 최대 비율(여백 확보).
_PRODUCT_FILL = 0.92


def _place_product(
    product: Image.Image, w: int, h: int, template: TemplateType, product_fill: float
) -> tuple[Image.Image, int, int]:
    """상품을 템플릿 박스에 비율 유지로 리사이즈하고 배치 좌표를 계산한다.

    product_fill(전략별 상품 비중)은 프레임 짧은 변 대비 상품 최대 변의 목표 크기로,
    템플릿 박스 한계와 함께 적용해 텍스트 영역 침범 없이 비중을 반영한다.
    """
    x0, y0, x1, y1 = _COMPOSE_PRODUCT_BOXES[template]
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
    product_cutout_bytes: bytes, template: TemplateType, size: AdSize, product_fill: float
) -> tuple[bytes, bytes]:
    """누끼 상품을 배치한 베이스 PNG와, 상품 실루엣만 보존하는 마스크 PNG를 만든다."""
    w, h = (int(v) for v in size.value.split("x"))
    product = Image.open(io.BytesIO(product_cutout_bytes)).convert("RGBA")
    product, x, y = _place_product(product, w, h, template, product_fill)

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


def composite_logo(image_bytes: bytes, logo_bytes: bytes, template: TemplateType) -> bytes:
    """로고를 광고 이미지에 합성하여 PNG bytes로 반환한다."""
    ad = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    _composite_logo_pil(logo, ad, template)
    buf = io.BytesIO()
    ad.save(buf, format="PNG")
    return buf.getvalue()
