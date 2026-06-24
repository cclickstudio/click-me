"""신규 매니지먼트/어시스턴트 인프라 단위 테스트 — DB·네트워크 불필요(순수/목).

- 조회기간 토글 검증(_valid_preset)
- 하이브리드 검색 RRF 융합(_fuse)
- 이상 스캔 mock 모드
- 체크포인터 미초기화 시 MemorySaver 폴백
"""

from __future__ import annotations

from types import SimpleNamespace

from api.routers import management as m
from domain.management.assistant.checkpointer import get_pg_checkpointer
from domain.management.assistant.retriever import KbRetriever
from domain.management.wiring import build_checkpointer


def test_valid_preset_allows_known_and_falls_back():
    assert m._valid_preset("last_30d") == "last_30d"
    assert m._valid_preset("this_month") == "this_month"
    assert m._valid_preset("maximum") == "maximum"
    assert m._valid_preset("garbage") == "maximum"  # 미허용 값 → 안전 폴백
    assert m._valid_preset(None) == "maximum"


def _row(i: int):
    return SimpleNamespace(id=i, source=f"s{i}.md", title=f"t{i}", chunk=f"c{i}")


def test_rrf_fuse_boosts_overlap_and_includes_keyword_only():
    vec = [_row(1), _row(2), _row(3)]  # 벡터 채널
    kw = [_row(2), _row(4)]  # 키워드 채널 — 2가 겹침, 4는 키워드 전용
    out = KbRetriever._fuse(vec, kw, k=4)
    sources = [r["source"] for r in out]
    assert out[0]["source"] == "s2.md"  # 두 채널 다 잡힌 청크가 최상위(RRF)
    assert "s4.md" in sources  # 키워드 전용도 결과에 포함
    assert all("score" in r for r in out)


async def test_anomaly_scan_mock_mode(monkeypatch):
    monkeypatch.setattr(m.settings, "use_mock", True, raising=False)
    r = await m.anomaly_scan()
    assert r["source"] == "mock"
    assert r["scanned"] == 0
    assert r["anomalies"] == []


def test_build_checkpointer_falls_back_to_memory():
    # 앱 시작 init 전(테스트) → PG 싱글턴 없음 → MemorySaver 폴백.
    assert get_pg_checkpointer() is None
    cp = build_checkpointer(SimpleNamespace())
    # langgraph는 MemorySaver를 InMemorySaver로 별칭 — 인메모리 계열이면 폴백 성공.
    assert "Memory" in cp.__class__.__name__
