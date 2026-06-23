# 캐러셀 카피 스키마 단위 테스트 (LLM 호출 없음 — 구조만 검증)
from domain.generator.pipeline.carousel_copy import (
    CAROUSEL_ROLES,
    CarouselScript,
    CarouselSlide,
)


def test_roles_fixed_five():
    assert len(CAROUSEL_ROLES) == 5
    assert CAROUSEL_ROLES[0] == "문제 제기"
    assert CAROUSEL_ROLES[-1] == "CTA"


def test_script_schema_roundtrip():
    script = CarouselScript(
        slides=[
            CarouselSlide(role="문제 제기", headline="피곤하세요?", body="아침이 무겁다면"),
            CarouselSlide(role="CTA", headline="지금 시작", body="첫 구매 할인", cta="구매하기"),
        ]
    )
    assert len(script.slides) == 2
    assert script.slides[0].cta is None
    assert script.slides[1].cta == "구매하기"
