"""노드 1 — 상품 분석: 핵심가치 / Pain Point / Benefit 추출."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from core.config import settings
from domain.generator.contracts.schemas import ProductAnalysis
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState

_llm = ChatOpenAI(
    model=settings.generator_text_model,
    api_key=settings.openai_api_key,
    temperature=0.3,
).with_structured_output(ProductAnalysis)

_SYSTEM = """당신은 광고 기획 전문가입니다. 상품 정보를 분석해 다음을 한국어로 추출하세요.
- core_values: 상품의 핵심 가치 3~5개
- pain_points: 타겟 소비자가 겪는 문제(Pain Point) 3~5개
- benefits: 구매 시 얻는 혜택(Benefit) 3~5개"""


async def analyze_product(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "product_analysis", 10, "상품 분석 중...")
    req = state["request"]
    prompt = (
        f"제품명: {req['product_name']}\n"
        f"제품 설명: {req['product_description']}\n"
        f"타겟: {req['target_audience']}\n"
        f"광고 목적: {req['campaign_objective']}"
    )
    result: ProductAnalysis = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
    return {"product_analysis": result.model_dump()}
