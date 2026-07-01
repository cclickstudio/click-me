# 광고 이미지 S3 영속화 유틸 테스트 — upload_bytes/presign_get를 모킹해 분기(S3·폴백·실패) 검증
from __future__ import annotations

import os

from domain.simulation.adapters import ad_image_store


async def test_persist_uploads_to_s3_and_returns_key(monkeypatch) -> None:
    calls: dict = {}

    async def fake_upload(data, key, content_type="image/png"):
        calls["upload"] = {"data": data, "key": key, "content_type": content_type}
        return key

    async def fake_presign(key, expires_in=3600):
        calls["presign"] = {"key": key, "expires_in": expires_in}
        return f"https://signed.example/{key}?sig=abc"

    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: True)
    monkeypatch.setattr(ad_image_store, "upload_bytes", fake_upload)
    monkeypatch.setattr(ad_image_store, "presign_get", fake_presign)

    vlm_ref, key = await ad_image_store.persist_ad_image(b"PNGDATA", "ad.jpg", "image/jpeg")

    assert key is not None and key.startswith("simulation/") and key.endswith(".jpg")
    assert vlm_ref == f"https://signed.example/{key}?sig=abc"
    # 영구 키로 업로드되고 업로드 content_type이 전달된다.
    assert calls["upload"]["key"] == key
    assert calls["upload"]["content_type"] == "image/jpeg"
    assert calls["presign"]["key"] == key
    assert calls["presign"]["expires_in"] == 3600


async def test_persist_falls_back_to_local_when_unconfigured(monkeypatch) -> None:
    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: False)

    vlm_ref, key = await ad_image_store.persist_ad_image(b"DATA", "ad.png", "image/png")
    try:
        # S3 미설정 → 로컬 임시파일 폴백(경로 존재·내용 보존), 영구 키는 없음.
        assert key is None
        assert os.path.exists(vlm_ref) and vlm_ref.endswith(".png")
        with open(vlm_ref, "rb") as f:
            assert f.read() == b"DATA"
    finally:
        if os.path.exists(vlm_ref):
            os.remove(vlm_ref)


async def test_persist_falls_back_on_upload_error(monkeypatch) -> None:
    async def boom(data, key, content_type="image/png"):
        raise RuntimeError("S3 down")

    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: True)
    monkeypatch.setattr(ad_image_store, "upload_bytes", boom)

    vlm_ref, key = await ad_image_store.persist_ad_image(b"X", "ad.png", "image/png")
    try:
        # 업로드 실패 시 로컬 폴백 + 키 없음(런 자체는 죽지 않음).
        assert key is None
        assert os.path.exists(vlm_ref)
    finally:
        if os.path.exists(vlm_ref):
            os.remove(vlm_ref)


async def test_persist_keeps_key_when_presign_fails(monkeypatch) -> None:
    async def fake_upload(data, key, content_type="image/png"):
        return key

    async def fail_presign(key, expires_in=3600):
        return None

    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: True)
    monkeypatch.setattr(ad_image_store, "upload_bytes", fake_upload)
    monkeypatch.setattr(ad_image_store, "presign_get", fail_presign)

    vlm_ref, key = await ad_image_store.persist_ad_image(b"X", "ad.png", "image/png")
    try:
        # presign 실패해도 영구 키는 보존(영속 가능), VLM 입력만 로컬 폴백.
        assert key is not None and key.startswith("simulation/")
        assert os.path.exists(vlm_ref)
    finally:
        if os.path.exists(vlm_ref):
            os.remove(vlm_ref)


async def test_presigned_for_passthrough_http(monkeypatch) -> None:
    # 이미 http URL이면 presign 호출 없이 그대로 통과.
    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: True)
    out = await ad_image_store.presigned_for("https://cdn.example/x.png")
    assert out == "https://cdn.example/x.png"


async def test_presigned_for_key_presigns(monkeypatch) -> None:
    async def fake_presign(key, expires_in=3600):
        return f"https://signed/{key}"

    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: True)
    monkeypatch.setattr(ad_image_store, "presign_get", fake_presign)

    out = await ad_image_store.presigned_for("simulation/abc.png")
    assert out == "https://signed/simulation/abc.png"


async def test_presigned_for_none_and_unconfigured(monkeypatch) -> None:
    assert await ad_image_store.presigned_for(None) is None
    # 키는 있으나 S3 미설정이면 표시 불가 → None(빈 상태 처리).
    monkeypatch.setattr(ad_image_store, "_s3_configured", lambda: False)
    assert await ad_image_store.presigned_for("simulation/abc.png") is None
