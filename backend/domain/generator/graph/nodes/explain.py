"""노드 6 — 생성 이유 설명: 적용 타겟 / 전략 / 템플릿 / 근거 (계획서 8장)."""

from __future__ import annotations

import asyncio
import json

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from core.config import settings
from domain.generator.contracts.schemas import CandidateExplanation
from domain.generator.contracts.templates import get_template
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState

_llm = ChatOpenAI(
    model=settings.generator_text_model,
    api_key=settings.openai_api_key,
    temperature=0.3,
).with_structured_output(CandidateExplanation)

_SYSTEM = """당신은 광고 기획자입니다. 생성된 광고 후보에 대해 사용자에게 보여줄 생성 이유 설명을 한국어로 작성하세요.
- applied_target: 어떤 타겟을 겨냥했는지 (1문장)
- applied_strategy: 적용된 광고 전략과 그 의도 (1~2문장)
- applied_template: 적용된 템플릿과 레이아웃 의도 (1문장)
- rationale: 이 조합이 이 상품·타겟에 효과적인 이유 (2~3문장)"""


async def explain_candidates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "explain", 95, "생성 이유 작성 중...")
    req = state["request"]

    async def explain_one(candidate: dict, qa_result: dict) -> dict:
        template = get_template(candidate["template_id"])
        prompt = (
            f"제품명: {req['product_name']}\n"
            f"타겟: {req['target_audience']}\n"
            f"광고 목적: {req['campaign_objective']}\n"
            f"전략: {json.dumps(candidate['strategy'], ensure_ascii=False)}\n"
            f"템플릿: Template {template.template_id} {template.name} — {template.description}\n"
            f"템플릿 선택 근거: {candidate.get('template_reason', '')}\n"
            f"카피: {json.dumps(candidate['copy'], ensure_ascii=False)}\n"
            f"QA 통과 여부: {qa_result['passed']}"
        )
        result: CandidateExplanation = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
        return result.model_dump()

    explanations = await asyncio.gather(
        *[
            explain_one(candidate, qa_result)
            for candidate, qa_result in zip(state["candidates"], state["qa_results"], strict=True)
        ]
    )
    return {"explanations": list(explanations)}
