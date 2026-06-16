import base64

from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.pipeline_schemas import ImageAnalysis
from tools.utils import safe_json_loads, str_or_none

_client = AsyncOpenAI(timeout=60.0)

_PROMPT = """\
Analyze this advertisement background image and return JSON only:
{
  "dominant_colors": ["#hex1", "#hex2", "#hex3"],
  "brightness": "dark|medium|light",
  "mood": "one-line mood description",
  "composition": "one-line description of subject placement and visual weight",
  "clear_zones": "describe which areas (top/bottom/left/right %) are visually uncluttered",
  "suggested_text_color": "#hex"
}

For suggested_text_color: choose a color that gives strong contrast \
against the overall image tone."""


@traceable(name="ImageAnalyzer", metadata={"pipeline": "generator"})
async def analyze_image(image_bytes: bytes) -> ImageAnalysis:
    b64 = base64.b64encode(image_bytes).decode()

    response = await _client.chat.completions.create(
        model="gpt-4o",
        max_tokens=300,
        temperature=0.1,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                            "detail": "low",
                        },
                    },
                    {"type": "text", "text": _PROMPT},
                ],
            }
        ],
        response_format={"type": "json_object"},
    )

    raw = safe_json_loads(response.choices[0].message.content, fallback="{}")

    colors = raw.get("dominant_colors", [])
    if not isinstance(colors, list):
        colors = []

    return ImageAnalysis(
        dominant_colors=colors[:3] if colors else ["#FFFFFF"],
        brightness=str_or_none(raw.get("brightness")) or "medium",
        mood=str_or_none(raw.get("mood")) or "",
        composition=str_or_none(raw.get("composition")) or "",
        clear_zones=str_or_none(raw.get("clear_zones")) or "",
        suggested_text_color=str_or_none(raw.get("suggested_text_color")) or "#FFFFFF",
    )
