# 이미지·전략에 맞는 광고 카피(헤드라인/본문/CTA)를 생성하는 노드 (factory LLM 경유)
from __future__ import annotations

from langsmith import traceable

from domain.generator.contracts.enums import TemplateType
from domain.generator.contracts.pipeline_schemas import (
    AdCopy,
    ProductAnalysis,
    StrategyOutput,
)
from domain.generator.llm.factory import build_text_llm

_TEMPLATE_COPY_GUIDE: dict[TemplateType, str] = {
    TemplateType.A: (
        "하단 오버레이 레이아웃. 헤드라인은 강렬하고 간결하게, "
        "본문은 핵심 혜택 1~2문장, CTA는 행동 유도."
    ),
    TemplateType.B: (
        "오버레이 레이아웃. 헤드라인은 이미지 상단에 pill 스크림으로 강조되므로 "
        "긴급성·이벤트 중심으로 짧고 임팩트 있게 (10자 이내 권장). "
        "본문은 하단 오버레이에 배치되어 부가 설명 역할."
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


@traceable(name="CopyGenerator", metadata={"pipeline": "generator"})
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
