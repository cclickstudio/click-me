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
    # 상품 이미지 직접 주입 (테스트용 — 추후 S3 키 다운로드로 전환)
    product_image_bytes: bytes | None
    # 개선모드 — 전략 노드가 만든 개선 컨텍스트(카피·이미지 생성까지 전달)
    improvement_context: str | None
    # 개선모드 — 기존 광고 이미지 bytes (existing_ad_s3_key에서 로드, openai edit/gemini 멀티모달 입력)
    existing_ad_bytes: bytes | None
