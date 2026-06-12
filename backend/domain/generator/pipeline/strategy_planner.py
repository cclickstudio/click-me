from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.enums import AdStrategy
from domain.generator.contracts.schemas import ProductAnalysis, StrategyOutput
from tools.utils import safe_json_loads, str_or_none

_client = AsyncOpenAI(timeout=60.0)

_STRATEGY_LABELS = {
    AdStrategy.BENEFIT: "혜택 강조",
    AdStrategy.PROBLEM_SOLVING: "문제 해결",
    AdStrategy.SOCIAL_PROOF: "사회적 증거",
}

_SYSTEM = """\
당신은 퍼포먼스 마케팅 전문가입니다.
제품 분석 결과를 바탕으로 효과적인 광고 전략 2종을 수립하고, 각 전략에 맞는 광고 문구를 작성합니다.
반드시 JSON 형식으로만 응답하세요."""

_USER_TEMPLATE = """\
아래 제품 분석 결과를 바탕으로 서로 다른 광고 전략 2종을 수립하세요.

## 제품 분석
제품명: {product_name}
핵심 가치: {core_values}
Pain Points: {pain_points}
혜택: {benefits}
타겟: {target_audience}
광고 목적: {objective}

## 사용 가능한 전략
- benefit: 혜택 강조
- problem_solving: 문제 해결
- social_proof: 사회적 증거

## 응답 형식
서로 다른 전략 2개를 선택하고 각각에 대해 아래 JSON 배열로 반환하세요:
[
  {{
    "strategy": "전략 코드",
    "strategy_description": "전략 설명 (1문장)",
    "headline": "광고 헤드라인 (20자 이내)",
    "body": "광고 본문 (50자 이내)",
    "cta": "CTA 문구 (10자 이내)",
    "rationale": "이 전략을 선택한 근거 (2~3문장)"
  }},
  {{ ... }}
]
{improvement_section}"""

_IMPROVE_SECTION = """\

## 개선 컨텍스트
{improvement_context}

기존 광고의 문제점을 해결하는 방향으로 전략을 수립하세요."""


@traceable(name="StrategyPlanner", metadata={"pipeline": "generator"})
async def plan_strategies(
    product_analysis: ProductAnalysis,
    improvement_context: str | None = None,
) -> list[StrategyOutput]:
    improvement_section = (
        _IMPROVE_SECTION.format(improvement_context=improvement_context)
        if improvement_context
        else ""
    )

    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.7,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    product_name=product_analysis.product_name,
                    core_values=", ".join(product_analysis.core_values),
                    pain_points=", ".join(product_analysis.pain_points),
                    benefits=", ".join(product_analysis.benefits),
                    target_audience=product_analysis.target_audience,
                    objective=product_analysis.objective,
                    improvement_section=improvement_section,
                ),
            },
        ],
        response_format={"type": "json_object"},
    )

    raw = safe_json_loads(response.choices[0].message.content, fallback="[]")
    items: list = raw if isinstance(raw, list) else raw.get("strategies", raw.get("items", []))

    outputs = []
    for item in items[:2]:
        strategy_str = str_or_none(item.get("strategy")) or "benefit"
        try:
            strategy = AdStrategy(strategy_str)
        except ValueError:
            strategy = AdStrategy.BENEFIT

        outputs.append(
            StrategyOutput(
                strategy=strategy,
                strategy_description=str_or_none(item.get("strategy_description"))
                or _STRATEGY_LABELS[strategy],
                headline=str_or_none(item.get("headline")) or "",
                body=str_or_none(item.get("body")) or "",
                cta=str_or_none(item.get("cta")) or "지금 바로 확인하기",
                rationale=str_or_none(item.get("rationale")) or "",
            )
        )

    return outputs
