# 🅰 오가닉 인사이트 읽기 Port (A-로컬, A만 소비)
"""ContentInsightsReader — 일반 게시물 인사이트 읽기 포트. contracts만 의존."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.management.comparison.schemas import PostInsights


class OrganicInsightsReader(Protocol):
    """오가닉 게시물 인사이트 읽기 — 구현체는 adapters/ 드롭인."""

    async def get_post_insights(self, post_id: str) -> PostInsights: ...
