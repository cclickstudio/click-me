# 슈퍼바이저 그래프 상태 — 챗 한 턴의 누적 상태(TypedDict).
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


class ChatState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    short_term: list[dict]
    long_term: list[dict]
    brand_profile: dict | None
    project_id: str | None
    user_id: str | None
    organization_id: str | None
    context_ids: dict
    route: str
    delegations: int
    sub_results: list[dict]
    citations: list[dict]
    pending_action: dict | None
    execution_result: dict | None
    approval_decision: dict | None
    final_answer: str
