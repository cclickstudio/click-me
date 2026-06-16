"""광고 생성 LangGraph 파이프라인 state."""

from __future__ import annotations

from typing import TypedDict


class GenerationState(TypedDict, total=False):
    generation_id: str
    request: dict  # GenerationCreateRequest.model_dump()
    product_analysis: dict  # pipeline_schemas.ProductAnalysis
    strategies: list[dict]  # StrategyOutput 3종
    plans: list[dict]  # StrategyPlan 3종 (strategies와 같은 순서, 템플릿 확정)
    candidates: list[dict]  # 후보 3종 (copy / s3_key 포함)
    qa_results: list[dict]  # QualityReport (candidates와 같은 순서)
    explanations: list[dict]  # CandidateExplanation (candidates와 같은 순서)
    error: str | None
