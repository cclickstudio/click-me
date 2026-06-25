# 🅱 HITL 선택 라운드 — rank()가 저장, package()가 검증·소비.
# v1 InMemory(단일 프로세스 데모/테스트 전용)
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True)
class SelectionRound:
    selection_token: str
    tenant_id: str
    candidate_ids: tuple[str, ...]
    expires_at: datetime
    created_at: datetime


class SelectionRoundRepository(Protocol):
    async def save(self, rnd: SelectionRound) -> None: ...
    async def claim(self, token: str, *, tenant_id: str, selected_id: str) -> SelectionRound: ...


class InMemorySelectionRoundStore:
    """v1 — 단일 프로세스 데모/테스트 전용. 재시작 시 미완료 selection 소실(=만료)."""

    def __init__(self) -> None:
        self._rounds: dict[str, SelectionRound] = {}
        self._claimed: set[str] = set()

    async def save(self, rnd: SelectionRound) -> None:
        self._rounds[rnd.selection_token] = rnd

    async def claim(self, token: str, *, tenant_id: str, selected_id: str) -> SelectionRound:
        rnd = self._rounds.get(token)
        if rnd is None:
            raise ValueError(f"unknown selection_token: {token}")
        if token in self._claimed:
            raise ValueError("duplicate claim — slate는 single-shot")
        if rnd.tenant_id != tenant_id:
            raise ValueError("tenant mismatch")
        if datetime.now(UTC) >= rnd.expires_at:
            raise ValueError("selection expired")
        if selected_id not in rnd.candidate_ids:
            raise ValueError("membership violation — 슬레이트 밖 candidate_id")
        self._claimed.add(token)
        return rnd
