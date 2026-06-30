# 개선 모드 기존 광고 이미지 로더 단위 테스트 — s3 key / http URL / 실패 폴백 (실 네트워크 없음)
import domain.generator.service.generator_service as gs


async def test_load_existing_ad_s3_key(monkeypatch):
    async def fake_download(key):
        assert key == "simulation/abc.png"
        return b"S3BYTES"

    monkeypatch.setattr(gs, "download_bytes", fake_download)
    out = await gs._load_existing_ad("simulation/abc.png")
    assert out == b"S3BYTES"


async def test_load_existing_ad_http(monkeypatch):
    class _Resp:
        content = b"HTTPBYTES"

        def raise_for_status(self):
            return None

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            assert url == "https://example.com/ad.png"
            return _Resp()

    monkeypatch.setattr(gs.httpx, "AsyncClient", lambda *a, **k: _Client())
    out = await gs._load_existing_ad("https://example.com/ad.png")
    assert out == b"HTTPBYTES"


async def test_load_existing_ad_failure_returns_none(monkeypatch):
    async def fake_download(key):
        raise RuntimeError("not found")

    monkeypatch.setattr(gs, "download_bytes", fake_download)
    out = await gs._load_existing_ad("simulation/missing.png")
    assert out is None  # 실패 시 None → 개선이 0부터 재생성으로 폴백
