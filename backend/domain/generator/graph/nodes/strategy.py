"""노드 2 — 광고 전략 생성: pipeline.strategy_planner로 서로 다른 전략 3종 수립.

개선 모드면 plan_strategies를 스킵하고 3-tier 분류기를 실행,
더미 StrategyPlan(template=None)을 1개 주입해 candidate_gen이 단일 후보를 자연스럽게 처리하게 한다.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.enums import AdStrategy, GenerationMode
from domain.generator.contracts.pipeline_schemas import ProductAnalysis, StrategyPlan
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.improvement_guide import classify_improvements
from domain.generator.pipeline.strategy_planner import plan_strategies


async def generate_strategies(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "strategy", 25, "광고 전략 생성 중...")
    req = state["request"]
    product_analysis = ProductAnalysis(**state["product_analysis"])

    if req.get("mode") == GenerationMode.IMPROVE:
        return await _handle_improve_mode(req, product_analysis)

    outputs = await plan_strategies(product_analysis)
    return {"strategies": [o.model_dump() for o in outputs]}


async def _handle_improve_mode(req: dict, product_analysis: ProductAnalysis) -> dict:
    """개선 모드 — 3-tier 분류기 + 더미 StrategyPlan(template=None) 주입."""
    directives = await classify_improvements(
        simulation_summary=req.get("simulation_summary"),
        plain_summary=req.get("plain_summary"),
        improvement_direction=req.get("improvement_direction"),
        fix_requests=req.get("fix_requests"),
    )

    improvement_context: str | None = None
    if directives:
        improvement_context = "[개선 지시문]\n" + "\n".join(f"- {d}" for d in directives)
        summary = req.get("simulation_summary")
        if summary:
            improvement_context += f"\n\n[시뮬레이션 결과 참고]\n{summary}"

    dummy_plan = StrategyPlan(
        strategy=AdStrategy.BENEFIT,
        template=None,
        strategy_description="시뮬레이션 기반 약점 보완",
        rationale="시뮬레이션 피드백과 수정 요청을 반영해 약점을 보완한 새 광고 이미지를 생성합니다.",
    )

    result: dict = {
        "strategies": [
            {
                "strategy": dummy_plan.strategy.value,
                "strategy_description": dummy_plan.strategy_description,
                "rationale": dummy_plan.rationale,
            }
        ],
        # select_templates를 건너뛰므로 plans를 직접 주입
        "plans": [dummy_plan.model_dump()],
    }
    if improvement_context:
        result["improvement_context"] = improvement_context

    return result
