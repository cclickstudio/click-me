from domain.generator.contracts.enums import AdStrategy, TemplateType

# 전략 → 템플릿 매핑 (규칙 기반)
# A: 제품 강조 — 혜택/문제해결처럼 제품 자체를 내세우는 전략
# B: 이벤트 강조 — 긴급성/FOMO처럼 행동 유도가 핵심인 전략
# C: 브랜드 강조 — 사회적 증거/감성처럼 신뢰·감성을 내세우는 전략
_STRATEGY_TEMPLATE_MAP: dict[AdStrategy, TemplateType] = {
    AdStrategy.BENEFIT: TemplateType.A,
    AdStrategy.PROBLEM_SOLVING: TemplateType.A,
    AdStrategy.URGENCY: TemplateType.B,
    AdStrategy.SOCIAL_PROOF: TemplateType.C,
    AdStrategy.EMOTIONAL: TemplateType.C,
}

_TEMPLATE_DESCRIPTIONS: dict[TemplateType, str] = {
    TemplateType.A: "제품 강조: 헤드라인 상단 / 제품 이미지 중앙 / CTA 하단",
    TemplateType.B: "이벤트 강조: 프로모션 문구 크게 / 제품 작게 / CTA 크게",
    TemplateType.C: "브랜드 강조: 로고·브랜드 컬러 강조 / 감성 이미지",
}


def select_template(strategy: AdStrategy) -> TemplateType:
    return _STRATEGY_TEMPLATE_MAP.get(strategy, TemplateType.A)


def describe_template(template: TemplateType) -> str:
    return _TEMPLATE_DESCRIPTIONS[template]
