# 이미지·전략에 맞는 광고 카피(헤드라인/본문/CTA)를 생성하는 노드 (factory LLM 경유)
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel

from domain.generator.contracts.enums import AdStrategy, TemplateType
from domain.generator.contracts.pipeline_schemas import (
    AdCopy,
    ProductAnalysis,
    StrategyOutput,
)
from domain.generator.llm.factory import build_text_llm

# 전략별 카피 서브 키워드 — 문구(헤드라인·본문)의 소재 방향. 시각 스타일이 아니라 카피 주제.
_STRATEGY_COPY_KEYWORDS: dict[AdStrategy, str] = {
    AdStrategy.BENEFIT: "할인, 쿠폰, 무료배송, 증정품, 첫 구매 혜택",
    AdStrategy.PROBLEM_SOLVING: "고민, 불편함, 개선, 변화, 해결",
    AdStrategy.SOCIAL_PROOF: "후기, 리뷰, 평점, 베스트셀러, 구매자 수",
    AdStrategy.EMOTIONAL: "감성, 행복, 추억, 여유, 특별한 순간",
    AdStrategy.FOMO: "오늘 마감, 한정 수량, 마지막 기회, 플래시 세일, 기간 한정",
}

_TEMPLATE_COPY_GUIDE: dict[TemplateType, str] = {
    TemplateType.A: (
        "하단 오버레이 레이아웃. 헤드라인은 강렬하고 간결하게, "
        "본문은 핵심 혜택 1~2문장, CTA는 행동 유도."
    ),
    TemplateType.B: (
        "오버레이 레이아웃. 헤드라인은 이미지 상단에 pill 스크림으로 강조되므로 "
        "긴급성·이벤트 중심으로 짧고 임팩트 있게 (10자 이내 권장). "
        "본문은 하단 오버레이에 배치되어 부가 설명 역할. CTA는 행동 유도."
    ),
    TemplateType.C: (
        "좌측 패널 레이아웃. 헤드라인·본문·CTA가 모두 좌측 컬러 패널 안에 들어가므로 "
        "브랜드 감성과 신뢰를 중심으로 작성. 줄바꿈 없이 간결하게."
    ),
}

_SYSTEM = """\
당신은 대한민국 퍼포먼스 마케팅 카피라이터입니다.
모든 출력은 반드시 자연스러운 한국어로 작성해야 합니다.
오탈자, 문법 오류, 의미 없는 단어 조합은 절대 허용되지 않습니다."""

_USER_TEMPLATE = """\
## 제품 정보
제품명: {product_name}
핵심 가치: {core_values}
혜택: {benefits}
타겟: {target_audience}

## 광고 전략
전략: {strategy_description}
전략 근거: {rationale}

## 레이아웃 가이드
{layout_guide}

## 작성 규칙 (엄격히 준수)
- 헤드라인: 실제 존재하는 한국어 단어만 사용, 20자 이내, 제품의 핵심 가치 전달
- 본문: 실제 존재하는 한국어 문장, 50자 이내, 자연스러운 문장 구조
- CTA: "지금 구매하기" / "자세히 보기" / "바로 시작하기" 등 명확한 한국어 행동 문구, 10자 이내
- 제품명({product_name})을 직접 사용하거나 자연스럽게 변형할 것
- 영어 단어를 한국어로 표기할 때 올바른 외래어 표기법 사용 (예: quality → 퀄리티)
- 의미 없는 단어 나열 금지

## 올바른 예시 (이와 같은 품질로 작성)
- 헤드라인: "매일 함께하는 프리미엄 텀블러" ✓
- 헤드라인: "퀄리티가 다른 보온 경험" ✓  ← quality = 퀄리티 (올바른 외래어)
- 헤드라인: "지금이 아니면 늦습니다" ✓
- 본문: "하루 종일 완벽한 온도를 유지하는 텀블러를 만나보세요." ✓
- CTA: "지금 구매하기" ✓ / "자세히 보기" ✓

## 잘못된 예시 (절대 사용 금지)
- "퀄랄리", "퀄랄리티" ✗  ← quality의 잘못된 음차
- "음다 음을", "스타일하게" ✗  ← 의미 없는 단어 조합
- "스마트 퀄랄리" ✗  ← 비문
{improvement_section}"""

_IMPROVEMENT_SECTION = """\

## 개선 방향 (최우선 반영)
{improvement_context}

기존 광고의 문제점을 해결하는 방향으로 카피를 작성하세요."""

_llm = build_text_llm(temperature=0.5, max_tokens=150).with_structured_output(AdCopy)


class _AdCopyBatch(BaseModel):
    copies: list[AdCopy]


_batch_llm = build_text_llm(temperature=0.5, max_tokens=450).with_structured_output(_AdCopyBatch)

_BATCH_USER_TEMPLATE = """\
## 제품 정보
제품명: {product_name}
핵심 가치: {core_values}
혜택: {benefits}
타겟: {target_audience}

## 작성 규칙 (엄격히 준수)
- 헤드라인: 실제 존재하는 한국어 단어만 사용, 20자 이내, 제품의 핵심 가치 전달
- 본문: 실제 존재하는 한국어 문장, 50자 이내, 자연스러운 문장 구조
- CTA: "지금 구매하기" / "자세히 보기" / "바로 시작하기" 등 명확한 한국어 행동 문구, 10자 이내
- 제품명({product_name})을 직접 사용하거나 자연스럽게 변형할 것
- 영어 단어를 한국어로 표기할 때 올바른 외래어 표기법 사용 (예: quality → 퀄리티)
- 의미 없는 단어 나열 금지

## 올바른 예시 (이와 같은 품질로 작성)
- 헤드라인: "매일 함께하는 프리미엄 텀블러" ✓
- 헤드라인: "퀄리티가 다른 보온 경험" ✓  ← quality = 퀄리티 (올바른 외래어)
- 헤드라인: "지금이 아니면 늦습니다" ✓
- 본문: "하루 종일 완벽한 온도를 유지하는 텀블러를 만나보세요." ✓
- CTA: "지금 구매하기" ✓ / "자세히 보기" ✓

## 잘못된 예시 (절대 사용 금지)
- "퀄랄리", "퀄랄리티" ✗  ← quality의 잘못된 음차
- "음다 음을", "스타일하게" ✗  ← 의미 없는 단어 조합
- "스마트 퀄랄리" ✗  ← 비문
{improvement_section}
---
아래 후보 3개 각각의 전략과 레이아웃에 맞는 카피를 작성해 copies 배열로 반환하세요.

## 후보 1
전략: {strategy_1}
전략 근거: {rationale_1}
서브 키워드(자연스럽게 1~2개 녹여서 반영): {keywords_1}
레이아웃: {layout_1}

## 후보 2
전략: {strategy_2}
전략 근거: {rationale_2}
서브 키워드(자연스럽게 1~2개 녹여서 반영): {keywords_2}
레이아웃: {layout_2}

## 후보 3
전략: {strategy_3}
전략 근거: {rationale_3}
서브 키워드(자연스럽게 1~2개 녹여서 반영): {keywords_3}
레이아웃: {layout_3}"""


@traceable(
    name="generator:generate_copies_batch",
    metadata={"pipeline": "generator", "prompt_version": "v1.0"},
)
async def generate_copies_batch(
    product_analysis: ProductAnalysis,
    strategy_outputs: list[tuple[StrategyOutput, TemplateType]],
    improvement_context: str | None = None,
) -> list[AdCopy]:
    improvement_section = (
        _IMPROVEMENT_SECTION.format(improvement_context=improvement_context)
        if improvement_context
        else ""
    )
    (s1, t1), (s2, t2), (s3, t3) = strategy_outputs
    prompt = _BATCH_USER_TEMPLATE.format(
        product_name=product_analysis.product_name,
        core_values=", ".join(product_analysis.core_values),
        benefits=", ".join(product_analysis.benefits),
        target_audience=product_analysis.target_audience,
        improvement_section=improvement_section,
        strategy_1=s1.strategy_description,
        rationale_1=s1.rationale,
        keywords_1=_STRATEGY_COPY_KEYWORDS.get(s1.strategy, ""),
        layout_1=_TEMPLATE_COPY_GUIDE[t1],
        strategy_2=s2.strategy_description,
        rationale_2=s2.rationale,
        keywords_2=_STRATEGY_COPY_KEYWORDS.get(s2.strategy, ""),
        layout_2=_TEMPLATE_COPY_GUIDE[t2],
        strategy_3=s3.strategy_description,
        rationale_3=s3.rationale,
        keywords_3=_STRATEGY_COPY_KEYWORDS.get(s3.strategy, ""),
        layout_3=_TEMPLATE_COPY_GUIDE[t3],
    )
    result = await _batch_llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
    return result.copies


@traceable(
    name="generator:generate_copy", metadata={"pipeline": "generator", "prompt_version": "v1.0"}
)
async def generate_copy(
    product_analysis: ProductAnalysis,
    strategy_output: StrategyOutput,
    template: TemplateType,
    improvement_context: str | None = None,
) -> AdCopy:
    improvement_section = (
        _IMPROVEMENT_SECTION.format(improvement_context=improvement_context)
        if improvement_context
        else ""
    )
    prompt = _USER_TEMPLATE.format(
        product_name=product_analysis.product_name,
        core_values=", ".join(product_analysis.core_values),
        benefits=", ".join(product_analysis.benefits),
        target_audience=product_analysis.target_audience,
        strategy_description=strategy_output.strategy_description,
        rationale=strategy_output.rationale,
        layout_guide=_TEMPLATE_COPY_GUIDE[template],
        improvement_section=improvement_section,
    )
    return await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
