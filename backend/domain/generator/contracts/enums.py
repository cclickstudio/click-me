from enum import Enum


class GenerationMode(str, Enum):
    CREATE = "create"
    IMPROVE = "improve"


class TemplateType(str, Enum):
    A = "A"  # 제품 강조: 헤드라인 상단 / 제품 중앙 / CTA 하단
    B = "B"  # 문제 해결 강조: 문제 상황 제시 상단 / 솔루션·제품 중앙 / CTA 하단
    C = "C"  # 브랜드 강조: 로고 강조 / 브랜드 컬러 활용


class AdStrategy(str, Enum):
    BENEFIT = "benefit"  # 혜택 강조
    PROBLEM_SOLVING = "problem_solving"  # 문제 해결
    SOCIAL_PROOF = "social_proof"  # 사회적 증거


class AdSize(str, Enum):
    SQUARE = "1024x1024"  # 1:1 — Instagram/Meta 피드 기본값
    LANDSCAPE = "1536x1024"  # 3:2 — Facebook 피드
    PORTRAIT = "1024x1536"  # 2:3 — Instagram/Facebook 스토리
