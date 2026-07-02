# 피드백 루프 — 집계(좋아요율·실패유형·최근 👎) 순수 로직 검증
"""management_kb_feedback를 소비해 RAG 품질을 가시화하는 _aggregate_feedback를 본다.

DB 미접촉(fake row) — summarize_feedback의 조회는 라이브/엔드포인트로 검증.
"""

from types import SimpleNamespace

from domain.management.assistant.history import _aggregate_feedback


def _row(rating, ftype=None, q="질문", a="답변", corrected=None):
    return SimpleNamespace(
        rating=rating, failure_type=ftype, question=q, answer=a, corrected_answer=corrected
    )


def test_counts_and_like_rate():
    rows = [_row(1), _row(1), _row(-1, "stale_doc"), _row(-1, "hallucinated_number")]
    out = _aggregate_feedback(rows, limit=20)
    assert out["total"] == 4
    assert out["likes"] == 2
    assert out["dislikes"] == 2
    assert out["like_rate"] == 0.5


def test_failure_type_breakdown_and_negatives():
    rows = [_row(-1, "stale_doc"), _row(-1, "stale_doc"), _row(-1, "wrong_tool")]
    out = _aggregate_feedback(rows, limit=20)
    assert out["failure_types"] == {"stale_doc": 2, "wrong_tool": 1}
    assert len(out["recent_negatives"]) == 3


def test_empty_feedback():
    out = _aggregate_feedback([], limit=20)
    assert out["total"] == 0
    assert out["like_rate"] is None
    assert out["recent_negatives"] == []


def test_negatives_respects_limit_but_breakdown_is_full():
    rows = [_row(-1, "x") for _ in range(5)]
    out = _aggregate_feedback(rows, limit=2)
    assert len(out["recent_negatives"]) == 2  # 샘플은 limit
    assert out["failure_types"]["x"] == 5  # 분해는 전체
