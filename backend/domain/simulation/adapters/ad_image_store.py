# 업로드 광고 이미지를 S3에 영속화하고 VLM 로드용 참조를 만든다(미설정·실패 시 로컬 폴백).
#
# 영구 식별자(s3 key)와 표시용 참조(presigned URL / 로컬 경로)를 구분해 반환한다.
# 저장은 key를(만료 없음), VLM 해석·표시는 presigned URL을 쓴다(_load_image와 맞물림).
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from urllib.parse import quote

from core.config import settings
from tools.storage.s3 import presign_get, upload_bytes

logger = logging.getLogger("clickme")

_PRESIGN_TTL = 3600  # 상세 페이지 조회·VLM 다운로드에 충분(1시간)


def _s3_configured() -> bool:
    """S3 버킷·자격증명이 모두 있으면 True(없으면 로컬 폴백)."""
    return bool(
        settings.s3_bucket_name and settings.aws_access_key_id and settings.aws_secret_access_key
    )


def _write_local(data: bytes, suffix: str) -> str:
    """업로드 바이트를 임시 파일로 저장하고 경로 반환(로컬 폴백)."""
    fd, path = tempfile.mkstemp(prefix="clickme_ad_", suffix=suffix)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    return path


async def persist_ad_image(
    data: bytes, filename: str | None, content_type: str | None
) -> tuple[str, str | None]:
    """업로드 바이트를 저장하고 (vlm_ref, s3_key)를 반환한다.

    - S3 설정 시: simulation/{uuid}{ext}로 업로드 → (presigned URL, s3_key).
      presign 실패 시 VLM 입력만 로컬 폴백하되 key는 그대로 반환(영속 가능).
    - S3 미설정·업로드 실패 시: 로컬 임시파일 경로 폴백 → (local_path, None). 기존 동작 유지.

    vlm_ref 는 _load_image 가 읽을 수 있는 참조(http URL 또는 로컬 경로),
    s3_key 는 DB에 영속할 영구 식별자(없으면 None).
    """
    suffix = os.path.splitext(filename or "")[1] or ".png"
    if not _s3_configured():
        logger.warning("S3 미설정 — 광고 이미지를 로컬 임시파일로 폴백 저장")
        return _write_local(data, suffix), None

    key = f"simulation/{uuid.uuid4().hex}{suffix}"
    try:
        await upload_bytes(data, key, content_type=content_type or "image/png")
    except Exception:
        logger.exception("S3 업로드 실패 — 로컬 임시파일로 폴백 저장")
        return _write_local(data, suffix), None

    presigned = await presign_get(key, expires_in=_PRESIGN_TTL)
    # presign 실패해도 key는 살아있음 → VLM 입력만 로컬로 채우고 영속 식별자는 유지.
    vlm_ref = presigned or _write_local(data, suffix)
    return vlm_ref, key


async def presigned_for(asset_ref: str | None) -> str | None:
    """저장된 asset 참조를 표시용 URL로 변환한다.

    http(s) URL이면 그대로(외부 URL·이미 presigned), 그 외(s3 key)면 presign_get으로 발급.
    로컬 임시 경로 등 presign 불가하면 None(빈 상태 처리).
    """
    if not asset_ref:
        return None
    if asset_ref.startswith(("http://", "https://")):
        return asset_ref
    # 로컬 파일 경로(과거 S3 미설정 시 폴백 잔재)는 S3 키가 아니다 — presign하면 엉터리 URL이
    # 되므로 제외. S3 키는 "simulation/...png"처럼 드라이브문자(:)·역슬래시·선행 슬래시가 없다.
    if asset_ref.startswith("/") or "\\" in asset_ref or ":" in asset_ref:
        return None
    if not _s3_configured():
        return None
    return await presign_get(asset_ref, expires_in=_PRESIGN_TTL)


def proxy_url_for(asset_ref: str | None) -> str | None:
    """저장된 asset 참조를 브라우저 표시용 URL로 변환한다(자격증명 노출 방지).

    S3 키면 백엔드 프록시 경로(/api/simulation/image?key=…)를 돌려준다 — presigned URL을
    브라우저에 직접 노출하지 않기 위함(제너·채팅 이미지와 동일 패턴).
    http(s) URL은 그대로(외부), 로컬 경로·None은 표시 불가이므로 None.
    """
    if not asset_ref:
        return None
    if asset_ref.startswith(("http://", "https://")):
        return asset_ref
    # 로컬 파일 경로(과거 S3 미설정 폴백 잔재)는 S3 키가 아니다.
    if asset_ref.startswith("/") or "\\" in asset_ref or ":" in asset_ref:
        return None
    return f"/api/simulation/image?key={quote(asset_ref, safe='')}"
