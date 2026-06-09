import json
from langsmith import traceable
from openai import AsyncOpenAI

from core.schemas import Persona, OCEAN, PersonaAttributes
from tools.utils import str_or_none, str_list, safe_json_loads

_client = AsyncOpenAI(timeout=60.0)

SYSTEM = """\
당신은 소비자 행동 심리학과 마케팅 리서치 전문가입니다.
Big Five OCEAN 성격 모델을 기반으로 실제 소비자처럼 행동하는 구체적인 페르소나를 생성합니다.
OCEAN 점수를 다양하게 배분하세요 (각 요인 CV > 0.3 필수, 전원 0.5 금지).
반드시 JSON 배열 형식으로만 응답하세요."""

USER_TEMPLATE = """\
아래 조건으로 페르소나 {count}명을 생성하세요.

## 광고 분석 결과 (참고용)
{ad_analysis_json}

## 생성 조건
- 세그먼트 분포: {segment_distribution}
- OCEAN CV > 0.3 필수, 극단 조합 포함: 고O+고E, 저O+저N, 고C+저A
- 광고 공명:거부:중립 = 40:20:40

각 페르소나에 persona_id (P_0001 형식), OCEAN, 인구통계, 행동패턴, 라이프스타일, 서사 컨텍스트 포함.
JSON 배열로만 응답하세요."""


@traceable(name="PersonaFactoryAgent", metadata={"prompt_version": "v1.0"})
async def run_persona_factory(
    simulation_id: str,
    count: int,
    ad_analysis: dict,
    segment_distribution: dict | None = None,
) -> list[Persona]:
    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": USER_TEMPLATE.format(
                    count=count,
                    ad_analysis_json=json.dumps(ad_analysis, ensure_ascii=False),
                    segment_distribution=json.dumps(segment_distribution or {}, ensure_ascii=False),
                ),
            },
        ],
    )

    parsed = safe_json_loads(response.choices[0].message.content, fallback="[]")
    raw_list = parsed if isinstance(parsed, list) else parsed.get("personas", list(parsed.values())[0] if parsed else [])
    personas: list[Persona] = []

    for i, raw in enumerate(raw_list):
        ocean_data = raw.get("ocean", raw.get("OCEAN", {}))
        attrs = raw.get("attributes", raw)

        personas.append(
            Persona(
                persona_id=raw.get("persona_id", f"P_{i+1:04d}"),
                segment=raw.get("segment", "unknown"),
                ocean=OCEAN(
                    openness=float(ocean_data.get("openness", 0.5)),
                    conscientiousness=float(ocean_data.get("conscientiousness", 0.5)),
                    extraversion=float(ocean_data.get("extraversion", 0.5)),
                    agreeableness=float(ocean_data.get("agreeableness", 0.5)),
                    neuroticism=float(ocean_data.get("neuroticism", 0.5)),
                ),
                attributes=PersonaAttributes(
                    age=int(attrs.get("age", 30)),
                    gender=str(attrs.get("gender", "미지정")),
                    region=str(attrs.get("region", "서울")),
                    occupation=str(attrs.get("occupation", "직장인")),
                    income_level=str(attrs.get("income_level", "중")),
                    education=str(attrs.get("education", "대졸")),
                    purchase_motivation=str(attrs.get("purchase_motivation", attrs.get("purchase_decision_style", "실용성"))),
                    price_sensitivity=float(attrs.get("price_sensitivity", 0.5)),
                    brand_loyalty=float(attrs.get("brand_loyalty", 0.5)),
                    impulse_buying_tendency=float(attrs.get("impulse_buying_tendency", 0.5)),
                    core_values=str_list(attrs.get("core_values")),
                    consumption_style=str_or_none(attrs.get("consumption_style")),
                    current_concern=str_or_none(attrs.get("current_concern")),
                    trigger_words=str_list(attrs.get("trigger_words")),
                    rejection_words=str_list(attrs.get("rejection_words")),
                    current_emotion=str_or_none(attrs.get("current_emotional_state", attrs.get("current_emotion"))),
                ),
                temperature=float(raw.get("temperature", 0.7)),
                seed=int(raw.get("seed", i * 1000)),
            )
        )

    return personas
