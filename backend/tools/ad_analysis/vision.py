"""Ad Understanding Agent 툴 — GPT-4o Vision으로 광고 구조화 분석."""

from langchain_core.tools import tool
from openai import AsyncOpenAI

client = AsyncOpenAI()


@tool
async def analyze_ad_image(image_url: str) -> dict:
    """광고 이미지를 GPT-4o Vision으로 분석하여 구조화 데이터를 반환합니다.

    Returns:
        copy: 광고 문구
        cta: Call-to-Action
        usp: Unique Selling Point
        emotion: 감정 요소
        color_palette: 주요 색상
        layout: 레이아웃 구조
    """
    # TODO: GPT-4o Vision API 호출
    raise NotImplementedError


@tool
async def analyze_ad_text(text: str) -> dict:
    """텍스트 광고를 분석하여 구조화 데이터를 반환합니다."""
    # TODO: GPT-4o 텍스트 분석
    raise NotImplementedError
