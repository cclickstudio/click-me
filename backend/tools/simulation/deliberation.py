from langsmith import traceable
from openai import AsyncOpenAI

from core.schemas import Persona
from tools.utils import safe_json_loads

_client = AsyncOpenAI(timeout=60.0)

SYSTEM = """\
당신은 소비자 페르소나가 광고를 본 후 내면에서 일어나는 인지적 처리 과정을 시뮬레이션합니다.
즉각 반응 이후 5~10초간의 생각 흐름입니다. 이성이 개입합니다.
반드시 JSON 형식으로만 응답하세요."""

USER_TEMPLATE = """\
다음 페르소나의 내면 처리 과정을 시뮬레이션하세요.

[페르소나]
OCEAN: O={O:.2f}, C={C:.2f}, E={E:.2f}, A={A:.2f}, N={N:.2f}
구매 동기: {purchase_motivation}
가격 민감도: {price_sensitivity:.2f}
브랜드 충성도: {brand_loyalty:.2f}
현재 고민: {current_concern}

[즉각 반응 결과]
첫 감정: {first_emotion}
본능 반응: {gut_reaction}

[광고 정보]
{ad_summary}

{{
  "supporting_thoughts": ["지지 생각 1", "지지 생각 2"],
  "opposing_thoughts": ["반대 생각 1", "반대 생각 2"],
  "value_alignment": "가치관 일치도 1문장",
  "information_gap": "더 알고 싶은 것 1문장",
  "final_attitude": "최종 내면 태도 1문장"
}}

JSON만 출력하세요."""


@traceable(name="DeliberationAgent", metadata={"prompt_version": "v1.0"})
async def run_deliberation(persona: Persona, exposure_output: dict, ad_analysis: dict) -> dict:
    strategic = ad_analysis.get("strategic_analysis", {})
    text_a = ad_analysis.get("text_analysis", {})

    ad_summary = (
        f"핵심 메시지: {strategic.get('key_message', '')}\n"
        f"USP: {strategic.get('usp', '')}\n"
        f"CTA: {text_a.get('cta', '')}"
    )

    content = USER_TEMPLATE.format(
        O=persona.ocean.openness,
        C=persona.ocean.conscientiousness,
        E=persona.ocean.extraversion,
        A=persona.ocean.agreeableness,
        N=persona.ocean.neuroticism,
        purchase_motivation=persona.attributes.purchase_motivation,
        price_sensitivity=persona.attributes.price_sensitivity,
        brand_loyalty=persona.attributes.brand_loyalty,
        current_concern=persona.attributes.current_concern or "없음",
        first_emotion=exposure_output.get("first_emotion", ""),
        gut_reaction=exposure_output.get("gut_reaction", ""),
        ad_summary=ad_summary,
    )

    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
    )

    return safe_json_loads(response.choices[0].message.content)
