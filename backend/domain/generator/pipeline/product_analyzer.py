from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.schemas import ProductAnalysis
from tools.utils import safe_json_loads, str_list, str_or_none

_client = AsyncOpenAI(timeout=60.0)

_SYSTEM = """\
당신은 15년 경력의 광고 마케팅 전략가입니다.
제품/서비스 정보를 분석해 광고 소재 생성에 필요한 핵심 데이터를 추출합니다.
반드시 JSON 형식으로만 응답하세요."""

_USER_TEMPLATE = """\
아래 제품/서비스 정보를 분석하세요.

제품명: {product_name}
설명: {description}
타겟: {target}
광고 목적: {objective}

다음 항목을 JSON으로 반환하세요:
- core_values: 제품의 핵심 가치 (문자열 배열, 최대 3개)
- pain_points: 타겟 고객의 불편/문제점 (문자열 배열, 최대 3개)
- benefits: 제품이 제공하는 혜택 (문자열 배열, 최대 3개)
- target_audience: 정리된 타겟 설명 (문자열)
- objective: 정리된 광고 목적 (문자열)"""


@traceable(name="ProductAnalyzer", metadata={"pipeline": "generator"})
async def analyze_product(
    product_name: str,
    description: str,
    target: str,
    objective: str,
) -> ProductAnalysis:
    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.3,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    product_name=product_name,
                    description=description,
                    target=target,
                    objective=objective,
                ),
            },
        ],
        response_format={"type": "json_object"},
    )

    raw = safe_json_loads(response.choices[0].message.content)

    return ProductAnalysis(
        product_name=product_name,
        core_values=str_list(raw.get("core_values")),
        pain_points=str_list(raw.get("pain_points")),
        benefits=str_list(raw.get("benefits")),
        target_audience=str_or_none(raw.get("target_audience")) or target,
        objective=str_or_none(raw.get("objective")) or objective,
    )
