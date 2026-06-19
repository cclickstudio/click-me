# 광고 카피를 7개 항목으로 품질 검증하는 노드 (factory LLM 경유)
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel

from domain.generator.contracts.pipeline_schemas import AdCopy, QualityCheckItem, QualityReport
from domain.generator.llm.factory import build_text_llm

_SYSTEM = """\
당신은 광고 품질 검증 전문가입니다.
광고 문구를 7개 항목으로 평가합니다."""

_USER_TEMPLATE = """\
아래 광고 문구를 7개 항목으로 검증하세요. 각 항목은 passed(bool)/score(0.0~1.0)/feedback(설명)으로 평가합니다.

헤드라인: {headline}
본문: {body}
CTA: {cta}
타겟: {target}

검증 기준:
- typo_check: 오타·비문 없음
- duplicate_check: 헤드라인/본문/CTA 간 문구 중복 없음
- cta_exists: CTA 문구가 명확히 존재하고 행동 유도
- readability: 누구나 쉽게 이해 가능한 문장
- target_fit: 타겟 고객에게 적합한 표현
- text_length: 헤드라인 20자 이내, 본문 50자 이내, CTA 10자 이내
- brand_consistency: 헤드라인/본문/CTA 전체에서 톤앤매너·표현 방식이 일관됨"""


class _QualityLLM(BaseModel):
    """LLM 구조화 출력 — overall_passed는 코드에서 계산."""

    typo_check: QualityCheckItem
    duplicate_check: QualityCheckItem
    cta_exists: QualityCheckItem
    readability: QualityCheckItem
    target_fit: QualityCheckItem
    text_length: QualityCheckItem
    brand_consistency: QualityCheckItem


_llm = build_text_llm(temperature=0.1).with_structured_output(_QualityLLM)


def _failed_item() -> QualityCheckItem:
    return QualityCheckItem(passed=False, score=0.0, feedback="품질 검증 호출 실패")


@traceable(
    name="generator:check_quality", metadata={"pipeline": "generator", "prompt_version": "v1.0"}
)
async def check_quality(
    ad_copy: AdCopy,
    target: str,
) -> QualityReport:
    prompt = _USER_TEMPLATE.format(
        headline=ad_copy.headline,
        body=ad_copy.body,
        cta=ad_copy.cta,
        target=target,
    )
    try:
        out: _QualityLLM = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
        items = out.model_dump()
        overall_passed = all(v["passed"] for v in items.values())
        return QualityReport(**items, overall_passed=overall_passed)
    except Exception:
        failed = _failed_item()
        return QualityReport(
            typo_check=failed,
            duplicate_check=failed,
            cta_exists=failed,
            readability=failed,
            target_fit=failed,
            text_length=failed,
            brand_consistency=failed,
            overall_passed=False,
        )
