# 자기교정 검색(CRAG-lite) 핵심 로직 — dedup·근거평가(grade) 단위 검증
"""검색 근거 평가/병합 헬퍼를 결정론으로 본다(LLM은 fake 주입). 충분성 평가 실패는 통과로 폴백.

end-to-end 교정 동작(재검색·신호)은 라이브로 검증 — 여기선 분기 로직만.
"""

import pytest

from domain.management.assistant.graph import _dedup, _grade_kb, _KbGrade


def test_dedup_removes_duplicate_source_title():
    hits = [
        {"source": "a.md", "title": "T1"},
        {"source": "a.md", "title": "T1"},  # 중복
        {"source": "b.md", "title": "T2"},
    ]
    assert len(_dedup(hits)) == 2


class _FakeGradeLLM:
    """with_structured_output → self, ainvoke → 미리 정한 _KbGrade."""

    def __init__(self, grade: _KbGrade) -> None:
        self._g = grade

    def with_structured_output(self, _schema):
        return self

    async def ainvoke(self, _msgs, config=None):
        return self._g


@pytest.mark.asyncio
async def test_grade_kb_returns_llm_verdict():
    llm = _FakeGradeLLM(_KbGrade(sufficient=False, rewrite="더 나은 쿼리"))
    g = await _grade_kb(llm, "q", [{"title": "x", "chunk": "y"}])
    assert g.sufficient is False
    assert g.rewrite == "더 나은 쿼리"


class _BoomLLM:
    def with_structured_output(self, _schema):
        raise RuntimeError("structured output 미지원")


@pytest.mark.asyncio
async def test_grade_kb_failure_treats_as_sufficient():
    """평가 실패 → sufficient=True(보수적: 확실한 부족일 때만 교정, 채팅 안 막음)."""
    g = await _grade_kb(_BoomLLM(), "q", [{"title": "x", "chunk": "y"}])
    assert g.sufficient is True
