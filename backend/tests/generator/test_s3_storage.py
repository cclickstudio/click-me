"""S3 스토리지 유틸 테스트 — 키 규칙 및 presigned URL (네트워크 호출 없음)."""

from tools.storage.s3 import candidate_key, presign_get, publish_key


def test_candidate_key():
    assert candidate_key("gen-1", 0) == "generated-ads/gen-1/candidate-0.png"


def test_publish_key():
    assert publish_key("gen-1", 2) == "generated-ads/gen-1/candidate-2-publish.jpg"


async def test_presign_get_contains_key_and_signature():
    url = await presign_get("generated-ads/gen-1/candidate-0.png")
    assert "generated-ads/gen-1/candidate-0.png" in url
    assert "Signature" in url
