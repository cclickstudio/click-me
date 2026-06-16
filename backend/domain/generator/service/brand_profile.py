"""브랜드 프로필 인메모리 캐시 — 로그인 없이 client_id(UUID)로 식별.

서버 재시작 시 소실됨 (결정 사항, DB 영속화는 추후).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class BrandProfile:
    brand_color: str | None = None
    brand_logo_key: str | None = None
    tone_and_manner: str | None = None


_store: dict[str, BrandProfile] = {}


def get_profile(client_id: str) -> BrandProfile:
    return _store.get(client_id, BrandProfile())


def save_profile(
    client_id: str,
    *,
    brand_color: str | None = None,
    brand_logo_key: str | None = None,
    tone_and_manner: str | None = None,
) -> BrandProfile:
    p = _store.get(client_id, BrandProfile())
    if brand_color is not None:
        p.brand_color = brand_color
    if brand_logo_key is not None:
        p.brand_logo_key = brand_logo_key
    if tone_and_manner is not None:
        p.tone_and_manner = tone_and_manner
    _store[client_id] = p
    return p
