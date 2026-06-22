# 제품 분석 결과로 광고 전략 3종을 수립하는 노드 (factory LLM 경유)
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel

from domain.generator.contracts.enums import AdStrategy
from domain.generator.contracts.pipeline_schemas import ProductAnalysis, StrategyOutput
from domain.generator.llm.factory import build_text_llm

_STRATEGY_LABELS = {
    AdStrategy.BENEFIT: "혜택 강조",
    AdStrategy.PROBLEM_SOLVING: "문제 해결",
    AdStrategy.SOCIAL_PROOF: "사회적 증거",
    AdStrategy.FOMO: "긴급성(FOMO)",
    AdStrategy.EMOTIONAL: "감성 접근",
}

_SYSTEM = """\
당신은 퍼포먼스 마케팅 전문가입니다.
제품 분석 결과를 바탕으로 효과적인 광고 전략 3종을 수립합니다."""

_USER_TEMPLATE = """\
아래 제품 분석 결과를 바탕으로 서로 다른 광고 전략 3종을 수립하세요.

## 제품 분석
제품명: {product_name}
핵심 가치: {core_values}
Pain Points: {pain_points}
혜택: {benefits}
타겟: {target_audience}
광고 목적: {objective}

## 사용 가능한 전략
- benefit: 혜택 강조 (제품의 핵심 혜택을 직접 소구) → 템플릿 A
- problem_solving: 문제 해결 (타겟의 Pain Point → 솔루션 제시) → 템플릿 A
- fomo: 긴급성 (한정 기간·수량, Fear of Missing Out) → 템플릿 B
- social_proof: 사회적 증거 (후기·인증·신뢰도 강조) → 템플릿 C
- emotional: 감성 접근 (라이프스타일·감성 이미지로 소구) → 템플릿 C

## 규칙
- 반드시 3개의 서로 다른 전략을 선택하세요.
- 템플릿 B(fomo)는 반드시 하나 포함하세요. 그래야 3개의 템플릿(A·B·C)이 모두 활용됩니다.
- 나머지 2개는 템플릿 A 계열(benefit 또는 problem_solving)과 템플릿 C 계열(social_proof 또는 emotional) 중 각 1개씩 선택하세요.
- 각 전략마다 strategy(전략 코드), strategy_description(1문장), rationale(2~3문장)을 작성하세요.
{improvement_section}"""

_IMPROVE_SECTION = """\

## 개선 컨텍스트
{improvement_context}

기존 광고의 문제점을 해결하는 방향으로 전략을 수립하세요."""


class _StrategyItem(BaseModel):
    strategy: str
    strategy_description: str
    rationale: str


class _StrategyList(BaseModel):
    strategies: list[_StrategyItem]


_llm = build_text_llm(temperature=0.7).with_structured_output(_StrategyList)


@traceable(
    name="generator:plan_strategies", metadata={"pipeline": "generator", "prompt_version": "v1.0"}
)
async def plan_strategies(
    product_analysis: ProductAnalysis,
    improvement_context: str | None = None,
) -> list[StrategyOutput]:
    improvement_section = (
        _IMPROVE_SECTION.format(improvement_context=improvement_context)
        if improvement_context
        else ""
    )
    prompt = _USER_TEMPLATE.format(
        product_name=product_analysis.product_name,
        core_values=", ".join(product_analysis.core_values),
        pain_points=", ".join(product_analysis.pain_points),
        benefits=", ".join(product_analysis.benefits),
        target_audience=product_analysis.target_audience,
        objective=product_analysis.objective,
        improvement_section=improvement_section,
    )

    try:
        out: _StrategyList = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
        items = out.strategies
    except Exception:
        items = []

    outputs: list[StrategyOutput] = []
    for item in items[:3]:
        try:
            strategy = AdStrategy(item.strategy)
        except ValueError:
            # 모델이 잘못된 코드를 주면 A·B·C 템플릿이 모두 나오도록 기본 전략으로 폴백
            strategy = (
                AdStrategy.BENEFIT
                if not outputs
                else AdStrategy.FOMO
                if len(outputs) == 1
                else AdStrategy.SOCIAL_PROOF
            )
        outputs.append(
            StrategyOutput(
                strategy=strategy,
                strategy_description=item.strategy_description or _STRATEGY_LABELS[strategy],
                rationale=item.rationale or "",
            )
        )

    # 결과가 비면(완전 실패) 최소 3종 기본 전략으로 보강
    _defaults = [AdStrategy.BENEFIT, AdStrategy.FOMO, AdStrategy.SOCIAL_PROOF]
    while len(outputs) < 3:
        s = _defaults[len(outputs)]
        outputs.append(
            StrategyOutput(strategy=s, strategy_description=_STRATEGY_LABELS[s], rationale="")
        )

    return outputs
