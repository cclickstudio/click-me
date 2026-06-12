from domain.generator.contracts.enums import AdStrategy, TemplateType

# 전략 → 템플릿 매핑 (규칙 기반)
# A: 제품 강조 — benefit / problem_solving (혜택·문제 해결 직접 소구)
# B: 이벤트 강조 — fomo (긴급성·프로모션 강조)
# C: 브랜드 강조 — social_proof / emotional (신뢰·감성 접근)
_STRATEGY_TEMPLATE_MAP: dict[AdStrategy, TemplateType] = {
    AdStrategy.BENEFIT: TemplateType.A,
    AdStrategy.PROBLEM_SOLVING: TemplateType.A,
    AdStrategy.FOMO: TemplateType.B,
    AdStrategy.SOCIAL_PROOF: TemplateType.C,
    AdStrategy.EMOTIONAL: TemplateType.C,
}

_TEMPLATE_DESCRIPTIONS: dict[TemplateType, str] = {
    TemplateType.A: "제품 강조: 헤드라인 상단 / 제품 이미지 중앙 / CTA 하단",
    TemplateType.B: "이벤트 강조: 프로모션·긴급성 상단 / 제품 이미지 중앙 / CTA 하단",
    TemplateType.C: "브랜드 강조: 로고·브랜드 컬러 강조 / 감성·사회적 증거 이미지",
}


def select_template(strategy: AdStrategy) -> TemplateType:
    return _STRATEGY_TEMPLATE_MAP.get(strategy, TemplateType.A)


def describe_template(template: TemplateType) -> str:
    return _TEMPLATE_DESCRIPTIONS[template]
