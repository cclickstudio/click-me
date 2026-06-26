# 슈퍼바이저 그래프 상태 — 챗 한 턴의 누적 상태(TypedDict).
from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import add_messages


def _merge_context(old: dict | None, new: dict | None) -> dict:
    """context_ids 리듀서 — 기존 값 유지, 새 입력의 non-null만 덮어쓴다.

    turn2의 null 값이 이전 ad_id를 지우지 못하게 막는다.
    """
    merged = dict(old or {})
    for k, v in (new or {}).items():
        if v is not None:
            merged[k] = v
    return merged


class ChatState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    short_term: list[dict]
    long_term: list[dict]
    brand_profile: dict | None
    project_id: str | None
    user_id: str | None
    organization_id: str | None
    context_ids: Annotated[dict, _merge_context]
    route: str
    delegations: int
    sub_results: list[dict]
    citations: list[dict]
    pending_action: dict | None
    execution_result: dict | None
    approval_decision: dict | None
    final_answer: str
