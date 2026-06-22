# 🅰 오가닉 인사이트 읽기 Port (A-로컬, A만 소비)
"""ContentInsightsReader — 일반 게시물 인사이트 읽기 포트. contracts만 의존."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.management.comparison.schemas import PostInsights, PredictionSnapshot


class OrganicInsightsReader(Protocol):
    """오가닉 게시물 인사이트 읽기 — 구현체는 adapters/ 드롭인."""

    async def get_post_insights(self, post_id: str) -> PostInsights: ...


class PredictionReader(Protocol):
    """집행 전 시뮬 예측 읽기 — 시뮬 디커플링 슬롯.

    지금은 MockPredictionReader, 시뮬 안정화 후 SimPredictionReader로 교체(wiring 한 줄).
    ad_id에 예측이 없으면 None(시뮬 미연결).
    """

    async def get_prediction(self, ad_id: str) -> PredictionSnapshot | None: ...
