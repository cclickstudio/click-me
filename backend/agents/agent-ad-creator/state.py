"""Ad Creator Agent — LangGraph 상태 정의 (7.8 목표)."""

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class DebateMessage(TypedDict):
    persona_id: str
    role: str    # advocate | critic | moderator
    content: str
    round: int


class AdCreatorState(TypedDict):
    brief: str                       # 사용자 입력 광고 니즈
    ad_type: str                     # text | image | video
    debate_personas: list[dict]      # 토론 참여 페르소나 5명
    debate_history: Annotated[list[DebateMessage], lambda a, b: a + b]
    debate_verdict: str              # 토론 투표 결과
    generated_ad: dict               # 생성된 광고 결과물
    messages: Annotated[list, add_messages]
