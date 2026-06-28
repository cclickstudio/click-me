# GeneratorReadClient — D1 계약 조회·검증
import httpx
import pytest

from domain.management.adapters.generator.client import (
    GeneratorReadClient,
    GeneratorUnavailableError,
    HandoffCandidate,
    InvalidGenerationError,
)

_OK = {
    "generation_id": "g1",
    "schema_version": "1",
    "status": "completed",
    "selected_candidate_id": "c1",
    "candidates": [
        {
            "candidate_id": "c1",
            "idx": 0,
            "strategy": {"angle": "s"},
            "template_id": "t",
            "copy": {"headline": "h", "body": "b", "cta": "사기"},
            "s3_key": "generator/images/g1/0.png",
        }
    ],
}


def _client(handler):
    return GeneratorReadClient(base_url="http://test", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_resolve_candidate_ok():
    client = _client(lambda req: httpx.Response(200, json=_OK))
    cand = await client.get_candidate("g1", "c1")
    assert isinstance(cand, HandoffCandidate)
    assert cand.s3_key == "generator/images/g1/0.png"
    assert cand.copy.headline == "h"


@pytest.mark.asyncio
async def test_not_found_raises_invalid_404():
    client = _client(lambda req: httpx.Response(404, json={"detail": "x"}))
    with pytest.raises(InvalidGenerationError) as ei:
        await client.get_candidate("gX", "c1")
    assert ei.value.http_status == 404


@pytest.mark.asyncio
async def test_not_completed_raises_409():
    client = _client(lambda req: httpx.Response(200, json={**_OK, "status": "running"}))
    with pytest.raises(InvalidGenerationError) as ei:
        await client.get_candidate("g1", "c1")
    assert ei.value.http_status == 409


@pytest.mark.asyncio
async def test_bad_schema_version_raises_409():
    client = _client(lambda req: httpx.Response(200, json={**_OK, "schema_version": "2"}))
    with pytest.raises(InvalidGenerationError) as ei:
        await client.get_candidate("g1", "c1")
    assert ei.value.http_status == 409


@pytest.mark.asyncio
async def test_candidate_not_in_generation_raises_404():
    client = _client(lambda req: httpx.Response(200, json=_OK))
    with pytest.raises(InvalidGenerationError) as ei:
        await client.get_candidate("g1", "c-other")
    assert ei.value.http_status == 404


@pytest.mark.asyncio
async def test_upstream_5xx_raises_unavailable():
    client = _client(lambda req: httpx.Response(503, json={"detail": "down"}))
    with pytest.raises(GeneratorUnavailableError):
        await client.get_candidate("g1", "c1")


def test_build_generator_client_uses_settings():
    from domain.management.wiring import build_generator_client

    class _S:
        internal_api_base_url = "http://example:8000"

    client = build_generator_client(_S())
    assert isinstance(client, GeneratorReadClient)
    assert client._base_url == "http://example:8000"
