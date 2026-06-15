"""노드 3 — 템플릿 선택: pipeline.template_selector 규칙 매핑으로 전략별 템플릿 확정."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.pipeline_schemas import StrategyOutput, StrategyPlan
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.template_selector import select_template


async def select_templates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "template", 35, "템플릿 선택 중...")
    plans = []
    for s in state["strategies"]:
        so = StrategyOutput(**s)
        plan = StrategyPlan(
            strategy=so.strategy,
            strategy_description=so.strategy_description,
            template=select_template(so.strategy),
            rationale=so.rationale,
        )
        plans.append(plan.model_dump())
    return {"plans": plans}
