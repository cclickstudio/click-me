# 토론 종료 후 Q&A — 저장된 패널·주제·발언 이력을 복원해 참가자별 답변을 순차 SSE로 흘린다.
#
# run_id 결과(panel·topic·debate)를 입력받아 DTO로 복원하고, 참가자마다 answer_question을
# to_thread로 순차 호출한다. 한 명 끝날 때마다 qa_utterance 이벤트(data: {json}\n\n)를 yield.
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator

from domain.simulation.contracts.debate_ports import DebaterPort
from domain.simulation.contracts.debate_schemas import (
    DebateParticipant,
    DebateTopic,
    Utterance,
)

logger = logging.getLogger("clickme")


def _sse(payload: dict) -> str:
    """dict → SSE 데이터 프레임(한글 보존)."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _history_by_persona(debate: dict | None) -> dict[str, list[Utterance]]:
    """result['debate']의 participants에서 persona_id별 utterances(history)를 복원."""
    history: dict[str, list[Utterance]] = {}
    if not debate:
        return history
    for pd in debate.get("participants", []):
        pid = pd.get("persona_id")
        if pid is None:
            continue
        history[pid] = [Utterance.model_validate(u) for u in pd.get("utterances", [])]
    return history


async def stream_qa(
    result: dict,
    question: str,
    debater: DebaterPort,
) -> AsyncIterator[str]:
    """패널 참가자가 한 명씩 순차로 질문에 답하는 Q&A를 SSE로 흘린다.

    result: get_result(run_id) 결과(panel·topic·debate 포함).
    참가자별 answer_question을 to_thread로 호출, 끝날 때마다 즉시 qa_utterance yield.
    예외는 참가자 단위로 잡아 '(응답 생성 실패)'로 내보내고 계속, 끝나면 qa_completed.
    """
    panel = result.get("panel") or {}
    participants = [DebateParticipant.model_validate(p) for p in panel.get("participants", [])]
    topic = DebateTopic.model_validate(result.get("topic") or {})
    history_map = _history_by_persona(result.get("debate"))

    for participant in participants:
        history = history_map.get(participant.persona_id, [])
        try:
            utt = await asyncio.to_thread(
                debater.answer_question, participant, question, topic, history
            )
        except Exception:
            logger.exception("Q&A 답변 실패 pid=%s", participant.persona_id)
            utt = Utterance(
                round=0,
                phase="질의응답",
                stance="neutral",
                text="(응답 생성 실패)",
                reason="",
                lever="",
            )
        yield _sse(
            {
                "event": "progress",
                "stage": "qa_utterance",
                "persona_id": participant.persona_id,
                "persona_name": participant.persona_name,
                "role": participant.role,
                "engine": participant.engine,
                "stance": utt.stance,
                "text": utt.text,
                "reason": utt.reason,
                "lever": utt.lever,
            }
        )
        await asyncio.sleep(0)  # 협조적 양보 — 스트리밍 느낌(한 명씩 도착)

    yield _sse({"event": "completed", "stage": "qa_completed"})
