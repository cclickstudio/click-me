# 전략별 디자인 스타일 프로필 — 텍스트 스타일·상품 비중·색을 한 곳에서 관리
# 텍스트 렌더(text_overlay)와 상품 배치(image_generator compose)가 공유하는 단일 소스.
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from domain.generator.contracts.enums import AdStrategy

TextStyle = Literal["box", "floating", "emotional"]
# KB Typography System(Pretendard 웨이트) — 실제 파일 해석·폴백은 text_overlay._resolve_font.
FontWeight = Literal[
    "thin", "extralight", "light", "regular", "medium", "semibold", "bold", "extrabold", "black"
]

# 텍스트 색(RGBA) 팔레트
_WHITE = (255, 255, 255, 255)
_LIGHT = (235, 235, 235, 255)
_DARK_GRAY = (51, 51, 51, 255)
_MID_GRAY = (90, 90, 90, 255)
_OFF_WHITE = (245, 240, 232, 255)
_BROWN = (120, 92, 72, 255)


@dataclass(frozen=True)
class StyleProfile:
    """전략 하나의 비주얼 정체성.

    - text_style: 텍스트 렌더 방식 (box=패널, floating=그림자, emotional=얇은폰트·여백).
    - product_fill: 누끼 compose에서 상품이 프레임에서 차지할 비중(0~1, 짧은 변 기준).
    - headline_color/body_color: 텍스트 색(RGBA). box 외 스타일은 2단계에서 사용.
    - accent_override: CTA·강조색 강제(브랜드컬러 무시). FOMO 코랄 레드 등.
    - highlight_numbers: 헤드라인 속 숫자(할인율·수량 등)를 강조색으로 렌더(혜택 강조용).
    - headline/body/cta_weight: KB Typography System의 전략별 폰트 웨이트. 보유 .woff2가 없으면
      text_overlay에서 가장 가까운 굵기로 폴백한다(누락 웨이트 추가 시 자동 적용).
    """

    text_style: TextStyle
    product_fill: float
    headline_color: tuple[int, int, int, int]
    body_color: tuple[int, int, int, int]
    accent_override: str | None = None
    highlight_numbers: bool = False
    headline_weight: FontWeight = "bold"
    body_weight: FontWeight = "regular"
    cta_weight: FontWeight = "bold"


# 전략 5종의 확정 프로필 (context-notes.md 표 + KB Typography System 기준).
# 폰트 웨이트는 KB의 전략별 헤드라인/본문/CTA 규칙을 그대로 반영.
STRATEGY_STYLE: dict[AdStrategy, StyleProfile] = {
    AdStrategy.BENEFIT: StyleProfile(
        "box",
        0.55,
        _WHITE,
        _LIGHT,
        highlight_numbers=True,
        headline_weight="extrabold",
        body_weight="regular",
        cta_weight="semibold",
    ),
    AdStrategy.PROBLEM_SOLVING: StyleProfile(
        "floating",
        0.25,
        _DARK_GRAY,
        _MID_GRAY,
        headline_weight="bold",
        body_weight="regular",
        cta_weight="medium",
    ),
    AdStrategy.SOCIAL_PROOF: StyleProfile(
        "floating",
        0.25,
        _DARK_GRAY,
        _MID_GRAY,
        headline_weight="semibold",
        body_weight="regular",
        cta_weight="medium",
    ),
    AdStrategy.EMOTIONAL: StyleProfile(
        "emotional",
        0.20,
        _OFF_WHITE,
        _BROWN,
        headline_weight="semibold",
        body_weight="light",
        cta_weight="regular",
    ),
    AdStrategy.FOMO: StyleProfile(
        "box",
        0.45,
        _WHITE,
        _WHITE,
        accent_override="#E63946",
        headline_weight="black",
        body_weight="semibold",
        cta_weight="extrabold",
    ),
}

# 프로필이 없는 전략이 들어와도 안전하게 동작하도록 기본값(box).
_DEFAULT_PROFILE = StyleProfile("box", 0.55, _WHITE, _LIGHT)


def get_style(strategy: AdStrategy) -> StyleProfile:
    """전략의 StyleProfile을 반환. 미등록 전략은 기본(box) 프로필."""
    return STRATEGY_STYLE.get(strategy, _DEFAULT_PROFILE)
