"""QA Harness 결정적 체크 테스트 (LLM 호출 없음)."""

from domain.generator.graph.nodes.qa import (
    check_copy_length,
    check_cta_presence,
    check_duplication,
)

COPY = {
    "headline": "여름 준비 끝",
    "subcopy": "시원한 바람, 조용한 밤",
    "benefit_text": "오늘만 30% 할인",
    "cta": "지금 구매하기",
}


def test_cta_presence_pass():
    assert check_cta_presence(COPY).passed


def test_cta_presence_fail_when_empty():
    result = check_cta_presence({**COPY, "cta": "  "})
    assert not result.passed
    assert result.name == "cta_presence"


def test_copy_length_pass():
    assert check_copy_length(COPY).passed


def test_copy_length_fail_when_headline_too_long():
    result = check_copy_length({**COPY, "headline": "가" * 30})
    assert not result.passed
    assert "headline" in result.detail


def test_duplication_pass_when_different():
    others = [{**COPY, "headline": "전혀 다른 문구입니다"}]
    assert check_duplication(COPY, others).passed


def test_duplication_fail_when_same_headline():
    result = check_duplication(COPY, [dict(COPY)])
    assert not result.passed
    assert "유사도" in result.detail
