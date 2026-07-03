# 생성 KB 하이브리드 RRF 융합 골든 — _fuse 순수함수 검증(DB·LLM 불필요)
"""management test_assistant_infra의 RRF 골든을 generator 리트리버에 미러한다."""

from types import SimpleNamespace

from domain.generator.assistant.retriever import GenKbRetriever


def _row(id_: str, dist: float | None = None) -> SimpleNamespace:
    base = {"id": id_, "source": f"src-{id_}", "title": f"t-{id_}", "chunk": f"c-{id_}"}
    if dist is not None:
        base["dist"] = dist
    return SimpleNamespace(**base)


def test_fuse_boosts_overlap():
    # 양 채널에 다 잡힌 'b'가 단일 채널 1위들('a','x')을 제친다.
    vec = [_row("a", 0.1), _row("b", 0.2)]
    kw = [_row("x"), _row("b")]
    out = GenKbRetriever._fuse(vec, kw, k=3)
    assert out[0]["source"] == "src-b"


def test_fuse_includes_keyword_only_with_none_cosine():
    vec = [_row("a", 0.1)]
    kw = [_row("kw-only")]
    out = GenKbRetriever._fuse(vec, kw, k=4)
    by_source = {o["source"]: o for o in out}
    assert "src-kw-only" in by_source
    assert by_source["src-kw-only"]["cosine_score"] is None


def test_fuse_cosine_score_from_dist():
    out = GenKbRetriever._fuse([_row("a", 0.25)], [], k=1)
    assert out[0]["cosine_score"] == 0.75
    assert out[0]["score"] > 0  # RRF 점수(코사인 아님)
