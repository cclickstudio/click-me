"""노드 1 — 상품 분석.

- create: pipeline.product_analyzer로 핵심가치/PainPoint/Benefit 추출
- improve: 시뮬레이션 요약·수정요청 기반으로 분석 컨텍스트만 구성(분석 LLM 생략)
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.product_analyzer import analyze_product as pipeline_analyze_product


async def analyze_product(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "product_analysis", 10, "상품 분석 중...")
    req = state["request"]

    if req.get("mode") == GenerationMode.IMPROVE:
        # 개선모드: 이미지 프롬프트 품질용 product_name만 유지, 나머지는 전략 노드의 개선 컨텍스트가 담당
        effective_name = req.get("product_name") or req.get("existing_ad_s3_key") or "기존 광고"
        analysis = ProductAnalysis(
            product_name=effective_name,
            core_values=[],
            pain_points=[],
            benefits=[],
            target_audience=req.get("target_audience") or "기존 타겟",
            objective="광고 개선",
        )
        return {"product_analysis": analysis.model_dump()}

    analysis = await pipeline_analyze_product(
        product_name=req["product_name"],
        description=req["product_description"],
        target=req["target_audience"],
        objective=req["campaign_objective"],
    )
    return {"product_analysis": analysis.model_dump()}
