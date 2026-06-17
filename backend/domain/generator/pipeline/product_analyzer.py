# 상품/서비스 정보를 광고 소재용 핵심 데이터로 분석하는 노드 (factory LLM 경유)
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel

from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.llm.factory import build_text_llm

_SYSTEM = """\
당신은 15년 경력의 광고 마케팅 전략가입니다.
제품/서비스 정보를 분석해 광고 소재 생성에 필요한 핵심 데이터를 추출합니다."""

_USER_TEMPLATE = """\
아래 제품/서비스 정보를 분석하세요.

제품명: {product_name}
설명: {description}
타겟: {target}
광고 목적: {objective}

다음 항목을 반환하세요:
- core_values: 제품의 핵심 가치 (문자열 배열, 최대 3개)
- pain_points: 타겟 고객의 불편/문제점 (문자열 배열, 최대 3개)
- benefits: 제품이 제공하는 혜택 (문자열 배열, 최대 3개)
- target_audience: 정리된 타겟 설명 (문자열)
- objective: 정리된 광고 목적 (문자열)"""


class _ProductAnalysisLLM(BaseModel):
    """LLM 구조화 출력 — product_name은 입력값이라 제외."""

    core_values: list[str]
    pain_points: list[str]
    benefits: list[str]
    target_audience: str
    objective: str


_llm = build_text_llm(temperature=0.3).with_structured_output(_ProductAnalysisLLM)


@traceable(name="ProductAnalyzer", metadata={"pipeline": "generator"})
async def analyze_product(
    product_name: str,
    description: str,
    target: str,
    objective: str,
) -> ProductAnalysis:
    prompt = _USER_TEMPLATE.format(
        product_name=product_name,
        description=description,
        target=target,
        objective=objective,
    )
    try:
        out: _ProductAnalysisLLM = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
        return ProductAnalysis(
            product_name=product_name,
            core_values=out.core_values[:3],
            pain_points=out.pain_points[:3],
            benefits=out.benefits[:3],
            target_audience=out.target_audience or target,
            objective=out.objective or objective,
        )
    except Exception:
        # 분석 실패 시에도 파이프라인이 멈추지 않도록 최소 정보로 폴백
        return ProductAnalysis(
            product_name=product_name,
            core_values=[],
            pain_points=[],
            benefits=[],
            target_audience=target,
            objective=objective,
        )
