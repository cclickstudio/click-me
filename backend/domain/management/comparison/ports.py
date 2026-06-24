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

    simulation_id로 해당 시뮬 런의 예측을 읽는다. tenant_id로 org 대조(타 org 노출 차단).
    예측이 없거나 org 불일치면 None(시뮬 미연결).
    """

    async def get_prediction(
        self, simulation_id: str, tenant_id: str
    ) -> PredictionSnapshot | None: ...
