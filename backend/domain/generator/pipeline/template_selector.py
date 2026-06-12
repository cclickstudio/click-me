from domain.generator.contracts.enums import AdStrategy, TemplateType

# 전략 → 템플릿 매핑 (규칙 기반)
# A: 제품 강조 — benefit (혜택 직접 소구)
# B: 문제 해결 강조 — problem_solving (Pain Point → 솔루션)
# C: 브랜드 신뢰 강조 — social_proof (후기·사회적 증거)
_STRATEGY_TEMPLATE_MAP: dict[AdStrategy, TemplateType] = {
    AdStrategy.BENEFIT: TemplateType.A,
    AdStrategy.PROBLEM_SOLVING: TemplateType.B,
    AdStrategy.SOCIAL_PROOF: TemplateType.C,
}

_TEMPLATE_DESCRIPTIONS: dict[TemplateType, str] = {
    TemplateType.A: "제품 강조: 헤드라인 상단 / 제품 이미지 중앙 / CTA 하단",
    TemplateType.B: "문제 해결 강조: 문제 상황 제시 상단 / 솔루션·제품 중앙 / CTA 하단",
    TemplateType.C: "브랜드 신뢰 강조: 로고·브랜드 컬러 강조 / 사회적 증거 이미지",
}


def select_template(strategy: AdStrategy) -> TemplateType:
    return _STRATEGY_TEMPLATE_MAP.get(strategy, TemplateType.A)


def describe_template(template: TemplateType) -> str:
    return _TEMPLATE_DESCRIPTIONS[template]
