"""노드 2 — 광고 전략 생성: 서로 다른 방향의 전략 3종 (계획서 7장)."""

from __future__ import annotations

import json
import logging

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from core.config import settings
from domain.generator.contracts.schemas import StrategySet
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState

logger = logging.getLogger("clickme")

_llm = ChatOpenAI(
    model=settings.generator_text_model,
    api_key=settings.openai_api_key,
    temperature=0.7,
).with_structured_output(StrategySet)

_SYSTEM = """당신은 광고 전략가입니다. 상품 분석 결과를 기반으로 서로 다른 방향의 광고 전략을 정확히 3개 생성하세요.
- strategy_type은 다음 중 선택하며 3개가 모두 달라야 합니다: benefit | fomo | social_proof | emotional | problem_solution
- 각 전략마다 한국어 전략명(name), 핵심 메시지(key_message), 이 상품·타겟에 이 전략을 쓰는 근거(rationale)를 작성하세요.
- 전략은 상품과 타겟 특성에 가장 효과적인 조합으로 AI가 직접 판단합니다."""


async def generate_strategies(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "strategy", 25, "광고 전략 생성 중...")
    req = state["request"]
    prompt = (
        f"제품명: {req['product_name']}\n"
        f"타겟: {req['target_audience']}\n"
        f"광고 목적: {req['campaign_objective']}\n"
        f"상품 분석: {json.dumps(state['product_analysis'], ensure_ascii=False)}"
    )
    result: StrategySet = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
    strategies = [s.model_dump() for s in result.strategies[:3]]

    types = [s["strategy_type"] for s in strategies]
    if len(set(types)) < len(types):
        logger.warning("전략 유형 중복 발생: %s", types)

    return {"strategies": strategies}
