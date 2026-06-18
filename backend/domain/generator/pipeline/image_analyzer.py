# 생성된 배경 이미지를 분석해 카피·텍스트 색 결정에 쓸 정보를 추출하는 노드 (factory vision LLM 경유)
from __future__ import annotations

import base64

from langchain_core.messages import HumanMessage
from langsmith import traceable

from domain.generator.contracts.pipeline_schemas import ImageAnalysis
from domain.generator.llm.factory import build_vision_llm

_PROMPT = """\
Analyze this advertisement background image and return structured fields:
- dominant_colors: up to 3 hex colors
- brightness: dark | medium | light
- mood: one-line mood description
- composition: one-line description of subject placement and visual weight
- clear_zones: describe which areas (top/bottom/left/right %) are visually uncluttered
- suggested_text_color: a hex color with strong contrast against the overall image tone"""


_llm = build_vision_llm(temperature=0.1).with_structured_output(ImageAnalysis)


@traceable(name="ImageAnalyzer", metadata={"pipeline": "generator"})
async def analyze_image(image_bytes: bytes) -> ImageAnalysis:
    b64 = base64.b64encode(image_bytes).decode()
    message = HumanMessage(
        content=[
            {"type": "text", "text": _PROMPT},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "low"},
            },
        ]
    )
    try:
        out: ImageAnalysis = await _llm.ainvoke([message])
        return ImageAnalysis(
            dominant_colors=(out.dominant_colors or ["#FFFFFF"])[:3],
            brightness=out.brightness or "medium",
            mood=out.mood or "",
            composition=out.composition or "",
            clear_zones=out.clear_zones or "",
            suggested_text_color=out.suggested_text_color or "#FFFFFF",
        )
    except Exception:
        # 분석 실패 시 안전한 기본값 — 카피·합성이 계속 진행되도록
        return ImageAnalysis(
            dominant_colors=["#FFFFFF"],
            brightness="medium",
            mood="",
            composition="",
            clear_zones="",
            suggested_text_color="#FFFFFF",
        )
