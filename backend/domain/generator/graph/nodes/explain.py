"""노드 5 — 생성 이유 설명: 적용 타겟 / 전략 / 템플릿 / 근거 (계획서 8장).

applied_target / applied_strategy / applied_template 은 state 데이터로 조립하고,
LLM 은 rationale(이 조합이 효과적인 이유) 한 필드만 생성한다.
"""

from __future__ import annotations

import asyncio

from langchain_core.runnables import RunnableConfig

from domain.generator.contracts.enums import TemplateType
from domain.generator.contracts.schemas import CandidateExplanation
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.llm.factory import build_text_llm
from domain.generator.pipeline.template_selector import describe_template

_llm = build_text_llm(temperature=0.3, max_tokens=200)

_SYSTEM = "당신은 광고 기획자입니다. 이 광고 조합이 해당 상품과 타겟에 효과적인 이유를 2~3문장으로 설명하세요."


async def explain_candidates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "explain", 95, "생성 이유 작성 중...")
    req = state["request"]

    async def explain_one(candidate: dict, qa_result: dict) -> dict:
        template = TemplateType(candidate["template_id"])
        strategy = candidate["strategy"]
        target = req.get("target_audience") or "기존 타겟"

        _last = target[-1] if target else ""
        _code = ord(_last) - 0xAC00
        particle = "을" if 0 <= _code <= 11171 and _code % 28 != 0 else "를"
        applied_target = f"{target}{particle} 주요 타겟으로 설정"
        applied_strategy = strategy.get("strategy_description", "")
        applied_template = describe_template(template)

        prompt = (
            f"제품명: {req.get('product_name') or '(개선모드)'}\n"
            f"타겟: {target}\n"
            f"전략: {strategy.get('strategy_description', '')}\n"
            f"전략 근거: {strategy.get('rationale', '')}\n"
            f"템플릿: Template {template.value} — {applied_template}\n"
            f"카피 헤드라인: {candidate['copy'].get('headline', '')}\n"
            f"QA 통과: {qa_result.get('overall_passed')}"
        )
        response = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
        rationale = response.content if hasattr(response, "content") else str(response)

        return CandidateExplanation(
            applied_target=applied_target,
            applied_strategy=applied_strategy,
            applied_template=applied_template,
            rationale=rationale,
        ).model_dump()

    explanations = await asyncio.gather(
        *[
            explain_one(candidate, qa_result)
            for candidate, qa_result in zip(state["candidates"], state["qa_results"], strict=True)
        ]
    )
    return {"explanations": list(explanations)}
