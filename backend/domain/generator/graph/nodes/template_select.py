"""노드 3 — 템플릿 선택: 전략별 템플릿 AI 자동 매핑 (계획서 14장)."""

from __future__ import annotations

import json

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from core.config import settings
from domain.generator.contracts.schemas import TemplateAssignmentSet
from domain.generator.contracts.templates import catalog_prompt, default_template_for
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState

_llm = ChatOpenAI(
    model=settings.generator_text_model,
    api_key=settings.openai_api_key,
    temperature=0.2,
).with_structured_output(TemplateAssignmentSet)

_SYSTEM = f"""당신은 광고 아트디렉터입니다. 각 광고 전략에 가장 적합한 템플릿을 카탈로그에서 하나씩 선택하세요.
전략마다 template_id(A/B/C)와 선택 근거(reason)를 한국어로 작성하세요.

## 템플릿 카탈로그
{catalog_prompt()}"""


async def select_templates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "template", 35, "템플릿 선택 중...")
    strategies = state["strategies"]
    prompt = f"광고 전략 목록:\n{json.dumps(strategies, ensure_ascii=False, indent=2)}"
    result: TemplateAssignmentSet = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])

    # 전략 순서에 맞춰 정렬 — LLM이 누락/오기한 경우 전략 적합 기본 템플릿으로 폴백
    by_type = {a.strategy_type: a.model_dump() for a in result.assignments}
    assignments = []
    for strategy in strategies:
        stype = strategy["strategy_type"]
        assignment = by_type.get(stype)
        if assignment is None or assignment["template_id"] not in ("A", "B", "C"):
            fallback = default_template_for(stype)
            assignment = {
                "strategy_type": stype,
                "template_id": fallback.template_id,
                "reason": f"{fallback.name} 템플릿 기본 매핑 (전략 적합 레이아웃)",
            }
        assignments.append(assignment)

    return {"template_assignments": assignments}
