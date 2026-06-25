# Tavily 웹검색 — KB에 없는/시의성 질문의 advisory 폴백 (키 없으면 graceful 빈 결과)
"""ReAct 그래프의 web_search 도구 본체. KB(신뢰) 우선, 부재·시의성 시 보조로 쓴다.

결과는 본질적으로 참고(advisory)다 — trust='advisory' + source_url + 조회시각을 달아 인용한다.
키(tavily_api_key) 없거나 호출 실패면 빈 리스트(search_kb의 except 패턴과 동일 — 채팅 안 끊김).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx

from core.config import settings

_TAVILY_URL = "https://api.tavily.com/search"


async def _tavily_fetch(api_key: str, query: str, k: int) -> dict:
    """Tavily Search API 호출 → 원본 JSON. 네트워크/HTTP 오류는 호출자가 잡는다."""
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": k,
        "search_depth": "basic",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(_TAVILY_URL, json=payload, timeout=15.0)
        resp.raise_for_status()
        return resp.json()


def _to_hit(r: dict) -> dict:
    """Tavily 결과 → 인용용 dict. 웹 결과는 항상 advisory."""
    return {
        "source": "web",
        "title": r.get("title", ""),
        "content": r.get("content", ""),  # LLM 답변 근거(인용 dict에선 미사용)
        "trust": "advisory",
        "source_url": r.get("url"),
    }


async def web_search(
    query: str,
    k: int = 3,
    *,
    api_key: str | None = None,
    fetch: Callable[[str, str, int], Awaitable[dict]] | None = None,
) -> list[dict]:
    """웹검색 → advisory 인용 dict 리스트. 키 없거나 실패면 [] (graceful).

    fetch를 주입하면 외부 호출 없이 테스트 가능(기본은 Tavily).
    """
    api_key = api_key or getattr(settings, "tavily_api_key", None)
    if not api_key:
        return []
    fetch = fetch or _tavily_fetch
    try:
        data = await fetch(api_key, query, k)
    except Exception:  # noqa: BLE001 — 웹검색 실패는 빈 결과로(채팅 안 끊김)
        return []
    return [_to_hit(r) for r in (data.get("results") or [])[:k]]
