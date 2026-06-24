"""노드 2 — 광고 전략 생성: pipeline.strategy_planner로 서로 다른 전략 3종 수립.

개선모드면 시뮬레이션 요약·수정요청을 improvement_context로 전달한다.
"""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.pipeline.improvement_guide import split_improvements
from domain.generator.pipeline.strategy_planner import plan_strategies


def _build_improvement_context(image_actions: list[str], summary: str | None) -> str | None:
    """이미지에 적용할 개선(우선순위순) + 시뮬 결과 요약(참고)으로 생성 컨텍스트를 구성."""
    parts: list[str] = []
    if image_actions:
        parts.append("[적용할 개선 — 우선순위순]\n" + "\n".join(f"- {a}" for a in image_actions))
    if summary:
        parts.append(f"[시뮬레이션 결과 참고]\n{summary}")
    return "\n\n".join(parts) if parts else None


async def generate_strategies(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "strategy", 25, "광고 전략 생성 중...")
    req = state["request"]
    product_analysis = ProductAnalysis(**state["product_analysis"])

    is_improve = req.get("mode") == GenerationMode.IMPROVE
    improvement_context: str | None = None
    guidance_lines: list[str] = []

    if is_improve:
        # 개선점을 이미지 적용 가능(생성에 반영) / 별도 조치 필요(가이드)로 분리
        try:
            split = await split_improvements(
                req.get("fix_requests"), req.get("improvement_direction")
            )
            image_actions, guidance_lines = split.image_actions, split.guidance
        except Exception:
            # 분류 실패 시 원문을 그대로 생성에 반영(생성이 막히지 않도록)
            image_actions = [
                v for v in (req.get("fix_requests"), req.get("improvement_direction")) if v
            ]
        improvement_context = _build_improvement_context(
            image_actions, req.get("simulation_summary")
        )

    outputs = await plan_strategies(product_analysis, improvement_context=improvement_context)
    result: dict = {"strategies": [o.model_dump() for o in outputs]}

    # 개선 컨텍스트를 state에 실어 카피·이미지 생성(candidate_gen)까지 전달
    if improvement_context:
        result["improvement_context"] = improvement_context

    # 이미지로 적용 어려운 개선점 가이드는 product_analysis JSONB에 함께 저장
    if guidance_lines:
        pa = dict(state["product_analysis"])
        pa["improvement_guidance"] = "\n".join(f"- {g}" for g in guidance_lines)
        result["product_analysis"] = pa

    return result
