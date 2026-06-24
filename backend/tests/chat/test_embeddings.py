# 임베딩 어댑터 — mock 결정성 + TEI(BGE-M3) HTTP 계약(hermetic).
import httpx
import pytest

from domain.chat.adapters.embeddings import MockEmbeddingProvider, TeiEmbeddingProvider


@pytest.mark.asyncio
async def test_mock_provider_is_deterministic_and_right_dim():
    p = MockEmbeddingProvider(dim=1024)
    a = await p.embed(["안녕"])
    b = await p.embed(["안녕"])
    assert len(a) == 1 and len(a[0]) == 1024
    assert a == b  # 같은 입력 → 같은 벡터
    c = await p.embed(["다른 문장"])
    assert c[0] != a[0]


@pytest.mark.asyncio
async def test_mock_provider_batch():
    p = MockEmbeddingProvider(dim=1024)
    out = await p.embed(["x", "y", "z"])
    assert len(out) == 3 and all(len(v) == 1024 for v in out)


@pytest.mark.asyncio
async def test_tei_provider_parses_embed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/embed"
        return httpx.Response(200, json=[[0.1] * 1024, [0.2] * 1024])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://tei")
    p = TeiEmbeddingProvider(base_url="http://tei", client=client)
    out = await p.embed(["a", "b"])
    assert len(out) == 2 and len(out[0]) == 1024
    assert out[0][0] == pytest.approx(0.1)
    await client.aclose()
