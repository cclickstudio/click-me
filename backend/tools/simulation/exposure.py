from langsmith import traceable
from openai import AsyncOpenAI

from core.schemas import Persona
from tools.utils import safe_json_loads

_client = AsyncOpenAI(timeout=60.0)

SYSTEM = """\
당신은 소비자 페르소나가 광고를 처음 접하는 순간을 시뮬레이션합니다.
이것은 3초 안에 일어나는 즉각적·본능적 반응입니다. 논리적 판단이 아닙니다.
반드시 JSON 형식으로만 응답하세요."""

USER_TEMPLATE = """\
다음 페르소나로 광고를 처음 봤을 때의 즉각적 반응을 시뮬레이션하세요.

[페르소나]
OCEAN: O={O:.2f}, C={C:.2f}, E={E:.2f}, A={A:.2f}, N={N:.2f}
인구통계: {age}세 {gender}, {region}, {occupation}
현재 감정 상태: {current_emotion}
트리거 단어: {trigger_words}
거부 단어: {rejection_words}

[광고 정보]
유형: {ad_type}
핵심 메시지: {key_message}
CTA: {cta}
USP: {usp}

{{
  "attention_capture": "시선이 어디에 가장 먼저 갔는지 1문장",
  "first_emotion": "첫 번째 감정 반응 1문장",
  "gut_reaction": "3초 안의 본능적 반응 2~3문장",
  "scroll_decision": "계속 볼지 결정과 이유 1문장"
}}

JSON만 출력하세요."""


@traceable(name="ExposureAgent", metadata={"prompt_version": "v1.0"})
async def run_exposure(persona: Persona, ad_analysis: dict) -> dict:
    strategic = ad_analysis.get("strategic_analysis", {})
    text_a = ad_analysis.get("text_analysis", {})

    content = USER_TEMPLATE.format(
        O=persona.ocean.openness,
        C=persona.ocean.conscientiousness,
        E=persona.ocean.extraversion,
        A=persona.ocean.agreeableness,
        N=persona.ocean.neuroticism,
        age=persona.attributes.age,
        gender=persona.attributes.gender,
        region=persona.attributes.region,
        occupation=persona.attributes.occupation,
        current_emotion=persona.attributes.current_emotion or "보통",
        trigger_words=", ".join(persona.attributes.trigger_words),
        rejection_words=", ".join(persona.attributes.rejection_words),
        ad_type=ad_analysis.get("input_type", "image"),
        key_message=strategic.get("key_message", ""),
        cta=text_a.get("cta", ""),
        usp=strategic.get("usp", ""),
    )

    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=persona.temperature,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": content},
        ],
        response_format={"type": "json_object"},
    )

    return safe_json_loads(response.choices[0].message.content)
