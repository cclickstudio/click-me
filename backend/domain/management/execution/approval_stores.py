# 승인 원장 인메모리 저장소 — use_mock·테스트용
"""DB 구현(db_stores.DbApprovalStore)과 같은 ApprovalStore 포트를 만족한다."""

from __future__ import annotations

from datetime import datetime

from domain.management.contracts.approval_ledger import ApprovalRecord


class InMemoryApprovalStore:
    """dict 기반 — Contract는 frozen이라 consume은 사본 교체로 마킹한다."""

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    async def put(self, record: ApprovalRecord) -> None:
        self._records[record.approval_id] = record

    async def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._records.get(approval_id)

    async def consume(self, approval_id: str, at: datetime) -> None:
        rec = self._records.get(approval_id)
        if rec is not None and rec.consumed_at is None:
            self._records[approval_id] = rec.model_copy(update={"consumed_at": at})
