from enum import Enum


class GenerationMode(str, Enum):
    CREATE = "create"
    IMPROVE = "improve"


class TemplateType(str, Enum):
    A = "A"  # 제품 강조: 헤드라인 상단 / 제품 이미지 중앙 / CTA 하단
    B = "B"  # 이벤트 강조: 프로모션·긴급성 상단 / 제품 중앙 / CTA 하단
    C = "C"  # 브랜드 강조: 로고·브랜드 컬러 / 감성·신뢰 이미지


class AdStrategy(str, Enum):
    BENEFIT = "benefit"  # 혜택 강조
    PROBLEM_SOLVING = "problem_solving"  # 문제 해결
    SOCIAL_PROOF = "social_proof"  # 사회적 증거
    FOMO = "fomo"  # 긴급성 (Fear of Missing Out)
    EMOTIONAL = "emotional"  # 감성 접근


class AdSize(str, Enum):
    SQUARE = "1024x1024"  # 1:1 — Instagram/Meta 피드 기본값
    LANDSCAPE = "1536x1024"  # 3:2 — Facebook 피드
    PORTRAIT = "1024x1536"  # 2:3 — Instagram/Facebook 스토리
