"""노드 2 — 광고 전략 생성: pipeline.strategy_planner로 서로 다른 전략 3종 수립.

개선 모드면 plan_strategies를 스킵하고 분류기를 실행해 5전략 중 1개를 동적으로 선택,
그 전략에 매핑된 실제 템플릿(A/B/C)으로 StrategyPlan을 1개 주입한다(candidate_gen은 그
1개로 단일 후보만 생성 — CREATE처럼 3종 동시 생성이 아니다).
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.pipeline_schemas import ProductAnalysis, StrategyPlan
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.improvement_guide import (
    ImprovementClassification,
    classify_improvements,
)
from domain.generator.pipeline.strategy_planner import _STRATEGY_LABELS, plan_strategies
from domain.generator.pipeline.template_selector import select_template

logger = logging.getLogger("clickme")


async def generate_strategies(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "strategy", 25, "광고 전략 생성 중...")
    req = state["request"]
    product_analysis = ProductAnalysis(**state["product_analysis"])

    if req.get("mode") == GenerationMode.IMPROVE:
        return await _handle_improve_mode(req, product_analysis)

    outputs = await plan_strategies(product_analysis)
    return {"strategies": [o.model_dump() for o in outputs]}


async def _handle_improve_mode(req: dict, product_analysis: ProductAnalysis) -> dict:
    """개선 모드 — 분류기로 지시문 + 전략(5종 중 1개) 선택, 그 전략의 실제 템플릿으로 StrategyPlan 1개 주입."""
    try:
        classification = await classify_improvements(
            simulation_summary=req.get("simulation_summary"),
            plain_summary=req.get("plain_summary"),
            improvement_direction=req.get("improvement_direction"),
            fix_requests=req.get("fix_requests"),
        )
    except Exception:
        # plan_strategies(CREATE 모드)와 동일하게 LLM 실패해도 파이프라인은 안 죽고
        # 기본 전략(BENEFIT)으로 폴백한다.
        logger.exception("개선 모드 전략 분류 실패 — 기본 전략(BENEFIT)으로 폴백")
        classification = ImprovementClassification()
    strategy = classification.strategy
    template = select_template(strategy)

    improvement_context: str | None = None
    if classification.directives:
        improvement_context = "[개선 지시문]\n" + "\n".join(
            f"- {d}" for d in classification.directives
        )
        summary = req.get("simulation_summary")
        if summary:
            improvement_context += f"\n\n[시뮬레이션 결과 참고]\n{summary}"

    dummy_plan = StrategyPlan(
        strategy=strategy,
        template=template,
        strategy_description=_STRATEGY_LABELS[strategy],
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
