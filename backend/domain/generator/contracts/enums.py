from enum import Enum


class GenerationMode(str, Enum):
    CREATE = "create"
    IMPROVE = "improve"


class TemplateType(str, Enum):
    A = "A"  # 제품 강조: 헤드라인 상단 / 제품 중앙 / CTA 하단
    B = "B"  # 이벤트 강조: 할인 문구 크게 / 제품 작게 / CTA 크게
    C = "C"  # 브랜드 강조: 로고 강조 / 브랜드 컬러 활용


class AdStrategy(str, Enum):
    BENEFIT = "benefit"                  # 혜택 강조
    PROBLEM_SOLVING = "problem_solving"  # 문제 해결
    SOCIAL_PROOF = "social_proof"        # 사회적 증거
    EMOTIONAL = "emotional"              # 감성 접근
    URGENCY = "urgency"                  # 긴급성(FOMO)


class AdSize(str, Enum):
    SQUARE = "1024x1024"     # 1:1 — Instagram/Meta 피드 기본값
    LANDSCAPE = "1536x1024"  # 3:2 — Facebook 피드
    PORTRAIT = "1024x1536"   # 2:3 — Instagram/Facebook 스토리
