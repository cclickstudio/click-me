"""노드 2 — 광고 전략 생성: pipeline.strategy_planner로 서로 다른 전략 3종 수립.

개선모드면 시뮬레이션 요약·수정요청을 improvement_context로 전달한다.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.strategy_planner import plan_strategies


def _build_improvement_context(req: dict) -> str:
    ctx = (
        f"기존 광고 S3 키: {req.get('existing_ad_s3_key')}\n"
        f"시뮬레이션 피드백: {req.get('simulation_summary')}"
    )
    if req.get("fix_requests"):
        ctx += f"\n추가 수정 요청: {req['fix_requests']}"
    return ctx


async def generate_strategies(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "strategy", 25, "광고 전략 생성 중...")
    req = state["request"]
    product_analysis = ProductAnalysis(**state["product_analysis"])

    improvement_context = (
        _build_improvement_context(req) if req.get("mode") == GenerationMode.IMPROVE else None
    )

    outputs = await plan_strategies(product_analysis, improvement_context=improvement_context)
    return {"strategies": [o.model_dump() for o in outputs]}
