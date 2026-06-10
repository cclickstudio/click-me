from langsmith import traceable
from openai import AsyncOpenAI

from core.schemas import AdAnalysisResult, StrategicAnalysis, TextAnalysis, VisualAnalysis
from tools.utils import safe_json_loads, str_list, str_or_none

_client = AsyncOpenAI(timeout=60.0)

SYSTEM = """\
당신은 15년 경력의 광고 전략 분석가입니다.
광고 소재를 분석하여 페르소나 반응 시뮬레이션에 필요한 구조화된 데이터를 추출합니다.
반드시 JSON 형식으로만 응답하세요. 설명 텍스트를 포함하지 마세요."""

USER_TEMPLATE = """\
다음 광고를 분석하세요.

[광고 유형]: {ad_type}
[광고 내용]: {ad_content}

headline, sub_headline, body_copy, cta, usp_list, emotional_keywords,
dominant_colors, visual_tone, layout_type, brand_elements,
target_demographic, purchase_stage (awareness|consideration|conversion),
appeal_type (rational|emotional|social), key_message,
likely_resonates_with (OCEAN 특성 목록), likely_resists_with, potential_objections,
trigger_concepts, confidence (0.0~1.0) 를 JSON으로 반환하세요."""


@traceable(name="AdUnderstandingAgent", metadata={"prompt_version": "v1.0"})
async def run_ad_understanding(
    ad_id: str,
    ad_type: str,
    ad_content: str,
) -> AdAnalysisResult:
    response = await _client.chat.completions.create(
        model="gpt-4o",
        temperature=0.1,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    ad_type=ad_type,
                    ad_content=ad_content,
                ),
            },
        ],
        response_format={"type": "json_object"},
    )

    raw = safe_json_loads(response.choices[0].message.content)

    return AdAnalysisResult(
        ad_id=ad_id,
        confidence=raw.get("confidence", 0.8),
        text_analysis=TextAnalysis(
            headline=str_or_none(raw.get("headline")),
            sub_headline=str_or_none(raw.get("sub_headline")),
            body=str_or_none(raw.get("body_copy")),
            cta=str_or_none(raw.get("cta")),
            usp_extracted=str_list(raw.get("usp_list")),
            emotional_keywords=str_list(raw.get("emotional_keywords")),
        ),
        visual_analysis=VisualAnalysis(
            dominant_colors=str_list(raw.get("dominant_colors")),
            emotional_tone=str_or_none(raw.get("visual_tone")),
            layout_type=str_or_none(raw.get("layout_type")),
            brand_elements=str_list(raw.get("brand_elements")),
        )
        if ad_type == "image"
        else None,
        strategic_analysis=StrategicAnalysis(
            target_demographic=str_or_none(raw.get("target_demographic")),
            purchase_stage_target=str_or_none(raw.get("purchase_stage")) or "conversion",
            usp=str_or_none(str_list(raw.get("usp_list"))[0]) if raw.get("usp_list") else None,
            key_message=str_or_none(raw.get("key_message")),
            likely_resonates_with=str_list(raw.get("likely_resonates_with")),
            likely_resists_with=str_list(raw.get("likely_resists_with")),
            potential_objections=str_list(raw.get("potential_objections")),
        ),
    )
