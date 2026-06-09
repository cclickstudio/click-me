"""Ad Management Agent — LangGraph 상태 정의."""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class PlatformTarget(TypedDict):
    platform: str    # instagram | twitter | youtube | facebook
    schedule: str    # ISO 8601 datetime or "now"
    action: str      # publish | unpublish


class ManagementState(TypedDict):
    ad_id: str
    targets: list[PlatformTarget]
    results: Annotated[list[dict], lambda a, b: a + b]
    messages: Annotated[list, add_messages]
