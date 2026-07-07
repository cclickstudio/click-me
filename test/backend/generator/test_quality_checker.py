# 광고 카피 규칙 기반 품질 검증(check_quality) 특성화 테스트 — 결정적 로직, LLM 호출 없음
from __future__ import annotations

from domain.generator.contracts.pipeline_schemas import AdCopy
from domain.generator.pipeline.quality_checker import check_quality


def _copy(headline: str, body: str, cta: str) -> AdCopy:
    return AdCopy(headline=headline, body=body, cta=cta)


def test_clean_copy_passes_without_warnings() -> None:
    report = check_quality(
        _copy("신선한 원두 커피", "아침을 깨우는 향", "지금 구매"), target="20대"
    )
    assert report.overall_passed is True
    assert report.policy_warnings == []
    assert report.text_length.passed and report.cta_exists.passed and report.duplicate_check.passed


def test_overlength_cta_fails_length_and_overall() -> None:
    report = check_quality(_copy("헤드라인", "본문", "지금 바로 구매하세요 어서"), target="일반")
    assert report.text_length.passed is False
    assert "CTA" in report.text_length.feedback
    assert report.overall_passed is False


def test_empty_cta_fails_cta_exists() -> None:
    report = check_quality(_copy("헤드라인", "본문", "   "), target="일반")
    assert report.cta_exists.passed is False
    assert report.overall_passed is False


def test_duplicate_headline_in_body_fails() -> None:
    report = check_quality(_copy("커피", "커피 향이 좋아요", "구매"), target="일반")
    assert report.duplicate_check.passed is False
    assert "헤드라인" in report.duplicate_check.feedback
    assert report.overall_passed is False


def test_policy_warning_does_not_fail_overall() -> None:
    # 금지어(100%)는 정책 경고만 남기고 overall_passed(길이·CTA·중복)에는 영향 없음.
    report = check_quality(_copy("100% 원두", "깊은 풍미", "구매하기"), target="일반")
    assert any("100%" in w for w in report.policy_warnings)
    assert report.overall_passed is True  # 정책 경고는 자문(advisory) — 통과 여부를 좌우하지 않음


def test_prohibited_term_inside_product_name_is_excised() -> None:
    # 금지어가 상품명 안에만 있으면 정책 경고에서 제외(상품명 제거 후 검사).
    copy = _copy("넘버원 커피", "맛있는 커피 한 잔", "주문")
    with_name = check_quality(copy, target="일반", product_name="넘버원")
    without_name = check_quality(copy, target="일반", product_name="")
    assert with_name.policy_warnings == []  # 상품명 제거 → 미경고
    assert any("넘버원" in w for w in without_name.policy_warnings)  # 제거 안 하면 경고
