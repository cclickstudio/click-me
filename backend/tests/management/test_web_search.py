# 매니지먼트 어시스턴트 web_search(Tavily) — 키 없음 graceful + 주입 fetch 검증
"""실제 네트워크 없이 검증: 키 없으면 빈 결과(채팅 안 끊김), 결과는 advisory 라벨.

fetch 주입으로 Tavily 호출을 스텁한다 — .env에 키가 있든 없든 결정론적으로 동작.
"""

import pytest

from domain.management.assistant.web_search import web_search


@pytest.mark.asyncio
async def test_no_key_returns_empty_and_skips_fetch(monkeypatch):
    """키 없으면 fetch 호출조차 안 하고 빈 결과."""
    monkeypatch.setattr(
        "domain.management.assistant.web_search.settings.tavily_api_key", None, raising=False
    )
    called = False

    async def _fetch(_api_key, _query, _k):
        nonlocal called
        called = True
        return {"results": []}

    res = await web_search("틱톡 최신 정책", fetch=_fetch)
    assert res == []
    assert called is False


@pytest.mark.asyncio
async def test_injected_fetch_returns_advisory_hits():
    async def _fetch(_api_key, _query, _k):
        return {
            "results": [
                {"title": "T1", "url": "https://a.example", "content": "C1"},
                {"title": "T2", "url": "https://b.example", "content": "C2"},
            ]
        }

    res = await web_search("q", k=2, api_key="tvly-test", fetch=_fetch)
    assert len(res) == 2
    assert all(h["trust"] == "advisory" for h in res)
    assert all(h["source"] == "web" for h in res)
    assert res[0]["source_url"] == "https://a.example"


@pytest.mark.asyncio
async def test_fetch_error_returns_empty():
    async def _boom(_api_key, _query, _k):
        raise RuntimeError("network down")

    res = await web_search("q", api_key="tvly-test", fetch=_boom)
    assert res == []
