# 생성결과 콜백 — 프론트가 보내는 [생성결과] 신호 처리(개선루프 HITL, LLM 판단 아님)
"""`[생성결과]` 접두사는 사용자 자연어가 아니라 위젯이 보내는 결과 콜백(프로토콜 신호)이다.

LLM 라우팅 대상이 아니므로 통합 에이전트를 거치지 않고 여기서 결정론으로 처리한다.
개선루프(loop_state)를 보고 재시뮬 approval 카드 또는 완료 메시지를 만든다.
"""

from __future__ import annotations

from domain.chat.loop_state import MAX_LOOP, get_loop_state

_PREFIX = "[생성결과]"


def is_result_callback(question: str | None) -> bool:
    """프론트가 보낸 생성결과 콜백인지 — [생성결과] 접두사로 결정론 판정."""
    return (question or "").lstrip().startswith(_PREFIX)


def handle(session_id: str | None, engine_label: str = "ClickMe") -> tuple[str, dict]:
    """생성결과 콜백 → (answer, meta). 왕복 여력 있으면 재시뮬 approval, 한도 도달이면 완료 안내."""
    loop = get_loop_state(session_id)
    loop.phase = "gen_done"
    if loop.loop_count >= MAX_LOOP:
        return (
            f"개선 루프 {loop.loop_count}/{MAX_LOOP}턴을 다 돌았어요. 새 시안까지 충분히 "
            "다듬었으니, 더 개선하려면 새 채팅에서 시작해 주세요.",
            {
                "source": "generator",
                "label": "개선 루프 완료",
                "engine": engine_label,
                "loop_done": True,
            },
        )
    return (
        "새 시안이 준비됐네요. 새 시안으로 반응을 다시 예측해볼까요?",
        {
            "source": "generator",
            "label": "결과 분석 · 재시뮬 제안",
            "engine": engine_label,
            "suggest": "simulation",
            "approval": {
                "action": "rerun_simulation",
                "label": "새 시안으로 재시뮬",
                "reasons": loop.weak_reasons,
            },
        },
    )
