# 공통 계약 재노출 파사드 — 정본은 core.assistant_contracts
"""오케스트레이터(api/assistant) 코드가 자연스러운 경로로 import하도록 재노출한다.
도메인 서브에이전트는 core.assistant_contracts에서 직접 가져온다(의존 방향 유지).
"""

from core.assistant_contracts import (
    Action,
    Intent,
    ProjectRef,
    StartedEvent,
    SubagentRequest,
    SubagentResult,
)

__all__ = [
    "Action",
    "Intent",
    "ProjectRef",
    "StartedEvent",
    "SubagentRequest",
    "SubagentResult",
]
