# 통합 채팅 에이전트 상태 — create_deep_agent에 미들웨어로 주입하는 커스텀 상태 채널
"""tool이 Command(update=...)로 쓰고, 실행 후 응답변환기가 읽는 추가 상태.

AgentState(messages 등)를 확장한다. middleware의 state_schema 속성으로 선언하면
create_deep_agent가 이 채널들을 그래프 상태에 합쳐준다(검증 완료 — top-level state_schema 불필요).
"""

from __future__ import annotations

from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, AgentState


def _merge_meta(left: dict | None, right: dict | None) -> dict:
    """sub_meta 누적 — 도메인 키별로 덮어쓰며 병합(한 턴에 여러 ask_* 호출 합성)."""
    return {**(left or {}), **(right or {})}


class UnifiedChatState(AgentState):
    """채팅 tool/콜백이 쓰는 추가 상태.

    입력 컨텍스트(session_id…memory_context) — 매 턴 invoke 시 주입. tool이 InjectedState로 읽어
    SubagentRequest·history 조회를 구성한다(closure로 못 잡는 per-turn 값).
    widget/source — 위젯 신호와 프론트 분기 키(마지막 기록 우선, 보통 한 턴에 하나).
    sub_meta — ask_management/simulation/generator가 누적하는 도메인 meta(병합).
    """

    # ── 입력 컨텍스트(per-turn) ──
    session_id: str | None
    user_id: str | None
    org_id: str | None
    project_id: str | None
    context_ad_id: str | None
    memory_context: str | None
    # 이번 턴 사용자 메시지에 이미지 첨부 여부 — run_generation이 상품 이미지 경로(폼) 분기에 쓴다.
    has_image: bool | None
    # ── 출력(tool/콜백이 기록) ──
    widget: dict | None
    source: str | None
    sub_meta: Annotated[dict, _merge_meta]


class ChatStateMiddleware(AgentMiddleware):
    """UnifiedChatState 필드를 그래프 상태 채널로 선언하는 미들웨어."""

    state_schema = UnifiedChatState
