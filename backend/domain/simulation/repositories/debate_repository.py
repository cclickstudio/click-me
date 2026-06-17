# 토론(10-c) 영속화 — DebateResult를 persona_debates/participants/utterances 3테이블로 저장
#
# 순수 매핑(build_debate_rows)과 DB 저장(DebateRepository.save)을 분리 — 매핑은 DB 없이 검증 가능.
# simulation_id FK(NOT NULL) 때문에 실제 simulations 행이 있는 운영 경로에서만 저장된다.
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from core.models import PersonaDebate, PersonaDebateParticipant, PersonaDebateUtterance
from domain.simulation.contracts.debate_schemas import DebateResult


def _as_uuid(value: str) -> uuid.UUID:
    """식별자 문자열을 UUID로 — UUID 형식이면 그대로, 아니면 결정적 uuid5."""
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(uuid.NAMESPACE_OID, value or "clickme-debate")


def build_debate_rows(
    simulation_id: str, debate: DebateResult
) -> tuple[dict, list[dict], list[dict]]:
    """DebateResult → (debate_row, participant_rows, utterance_rows) 순수 매핑(DB 무관, 검증용)."""
    models = debate.models or {}
    debate_row = {
        "simulation_id": simulation_id,
        "topic": debate.topic,
        "rounds_run": debate.rounds_run,
        "stop_reason": debate.stop_reason,
        "judge_model": models.get("judge"),
        "engines": models.get("engines"),
        "judge_log": {str(k): v for k, v in debate.round_summaries.items()},
        "final": debate.final.model_dump() if debate.final else None,
        "status": "COMPLETED",
    }
    participant_rows: list[dict] = []
    utterance_rows: list[dict] = []
    for p in debate.participants:
        participant_rows.append(
            {
                "persona_id": p.persona_id,
                "persona_name": p.persona_name,
                "persona_profile": p.persona_profile,
                "role": p.role,
                "engine": p.engine,
            }
        )
        for u in p.utterances:
            utterance_rows.append(
                {
                    "persona_id": p.persona_id,  # 저장 시 participant_id로 치환되는 연결 키
                    "round": u.round,
                    "phase": u.phase,
                    "stance": u.stance,
                    "text": u.text,
                    "reason": u.reason,
                    "lever": u.lever,
                }
            )
    return debate_row, participant_rows, utterance_rows


class DebateRepository:
    """토론 결과를 한 트랜잭션으로 저장. session_factory 주입(미주입 시 service가 영속화 생략)."""

    def __init__(self, session_factory: async_sessionmaker) -> None:
        self._session_factory = session_factory

    async def save(self, simulation_id: str, debate: DebateResult) -> uuid.UUID:
        """반환: 저장된 debate_id. participants→utterances 순으로 FK 연결."""
        debate_row, _, _ = build_debate_rows(simulation_id, debate)
        async with self._session_factory() as session:
            row = PersonaDebate(
                simulation_id=_as_uuid(simulation_id),
                topic=debate_row["topic"],
                rounds_run=debate_row["rounds_run"],
                stop_reason=debate_row["stop_reason"],
                judge_model=debate_row["judge_model"],
                engines=debate_row["engines"],
                judge_log=debate_row["judge_log"],
                final=debate_row["final"],
                status=debate_row["status"],
            )
            session.add(row)
            await session.flush()  # row.id 확보

            for p in debate.participants:
                part = PersonaDebateParticipant(
                    debate_id=row.id,
                    persona_id=p.persona_id,
                    persona_name=p.persona_name,
                    persona_profile=p.persona_profile,
                    role=p.role,
                    engine=p.engine,
                )
                session.add(part)
                await session.flush()  # part.id 확보
                for u in p.utterances:
                    session.add(
                        PersonaDebateUtterance(
                            debate_id=row.id,
                            participant_id=part.id,
                            round=u.round,
                            phase=u.phase,
                            stance=u.stance,
                            text=u.text,
                            reason=u.reason,
                            lever=u.lever,
                        )
                    )
            await session.commit()
            return row.id
