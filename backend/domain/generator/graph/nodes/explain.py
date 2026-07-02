# 노드 5 — 생성 이유 설명: 후보 3개를 LLM 1회 배치 호출로 처리
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from domain.generator.contracts.enums import TemplateType
from domain.generator.contracts.schemas import CandidateExplanation
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState
from domain.generator.llm.factory import build_text_llm
from domain.generator.pipeline.template_selector import describe_template


class _RationaleList(BaseModel):
    rationales: list[str]


_batch_llm = build_text_llm(temperature=0.3, max_tokens=600).with_structured_output(_RationaleList)

_SYSTEM = (
    "당신은 광고 기획자입니다. "
    "각 광고 후보가 해당 상품과 타겟에 효과적인 이유를 각각 2~3문장으로 설명하세요."
)


async def generate_explanations(
    product_name: str,
    target: str,
    rows: list[dict],
) -> list[dict]:
    """후보별 설명을 LLM 1회 배치 호출로 생성한다(렌더 이미지 불필요).

    rows 원소: {template: TemplateType, strategy_description, rationale, headline, qa_passed}.
    노드(state 기반)와 candidate_gen 병렬 선계산이 동일 입력으로 이 함수를 공유한다.
    """
    _last = target[-1] if target else ""
    _code = ord(_last) - 0xAC00
    particle = "을" if 0 <= _code <= 11171 and _code % 28 != 0 else "를"

    metas = []
    candidate_blocks = []
    for i, row in enumerate(rows, start=1):
        template = row["template"]
        applied_template = describe_template(template)
        applied_strategy = row["strategy_description"]

        metas.append(
            {
                "applied_target": f"{target}{particle} 주요 타겟으로 설정",
                "applied_strategy": applied_strategy,
                "applied_template": applied_template,
            }
        )
        candidate_blocks.append(
            f"## 후보 {i}\n"
            f"전략: {applied_strategy}\n"
            f"전략 근거: {row['rationale']}\n"
            f"템플릿: Template {template.value} — {applied_template}\n"
            f"카피 헤드라인: {row['headline']}\n"
            f"QA 통과: {row['qa_passed']}"
        )

    prompt = f"제품명: {product_name}\n타겟: {target}\n\n" + "\n\n".join(candidate_blocks)
    response = await _batch_llm.ainvoke([("system", _SYSTEM), ("user", prompt)])

    # LLM이 후보 수와 다른 개수의 rationale을 반환할 수 있어 개수에 맞춰 정렬한다.
    rationales = list(response.rationales)
    return [
        CandidateExplanation(
            applied_target=meta["applied_target"],
            applied_strategy=meta["applied_strategy"],
            applied_template=meta["applied_template"],
            rationale=(
                rationales[i]
                if i < len(rationales)
                else meta["applied_strategy"] or "해당 타겟에 적합한 전략을 적용했습니다."
            ),
        ).model_dump()
        for i, meta in enumerate(metas)
    ]


async def explain_candidates(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "explain", 95, "생성 이유 작성 중...")

    # candidate_gen이 이미지 생성과 병렬로 미리 만들어 둔 결과가 있으면 그대로 사용(LLM 재호출 없음).
    # pipeline 경로만 선계산하며, multimodal·캐러셀은 여기서 계산한다(폴백).
    pre = state.get("explanations")
    if pre:
        return {"explanations": pre}

    req = state["request"]
    target = req.get("target_audience") or "기존 타겟"
    product_name = req.get("product_name") or "(개선모드)"

    rows = [
        {
            "template": TemplateType(candidate["template_id"]),
            "strategy_description": candidate["strategy"].get("strategy_description", ""),
            "rationale": candidate["strategy"].get("rationale", ""),
            "headline": candidate["copy"].get("headline", ""),
            "qa_passed": qa_result.get("overall_passed"),
        }
        for candidate, qa_result in zip(state["candidates"], state["qa_results"], strict=True)
    ]
    return {"explanations": await generate_explanations(product_name, target, rows)}
