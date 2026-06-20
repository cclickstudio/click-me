# 토론(10-c) 영속화 — DebateResult를 persona_debates/participants/utterances 3테이블로 저장
#
# 순수 매핑(build_debate_rows)과 DB 저장(DebateRepository.save)을 분리 — 매핑은 DB 없이 검증 가능.
# simulation_id FK(NOT NULL) 때문에 실제 simulations 행이 있는 운영 경로에서만 저장된다.
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import selectinload

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


def _debate_meta(r: PersonaDebate) -> dict:
    """토론 1건 메타(목록 카드용) — 발언 제외, 주제·상태·결론 요약만."""
    final = r.final or {}
    return {
        "debate_id": str(r.id),
        "simulation_id": str(r.simulation_id),
        "topic": r.topic,
        "status": r.status,
        "rounds_run": r.rounds_run,
        "stop_reason": r.stop_reason,
        "headline": final.get("headline"),
        "plain_summary": final.get("plain_summary"),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _debate_detail(r: PersonaDebate) -> dict:
    """토론 상세(채팅·결과 복원용) — participants + 라운드순 발언 + judge_log + final."""
    pinfo = {p.id: p for p in r.participants}
    utts = sorted(r.utterances, key=lambda u: (u.round, u.created_at or r.created_at))
    utterances = []
    for u in utts:
        p = pinfo.get(u.participant_id)
        utterances.append(
            {
                "round": u.round,
                "phase": u.phase,
                "stance": u.stance,
                "text": u.text,
                "reason": u.reason,
                "lever": u.lever,
                "persona_id": p.persona_id if p else None,
                "persona_name": p.persona_name if p else None,
                "role": p.role if p else None,
                "engine": p.engine if p else None,
            }
        )
    return {
        **_debate_meta(r),
        "models": {"judge": r.judge_model, "engines": r.engines or []},
        "round_summaries": r.judge_log or {},
        "final": r.final,
        "participants": [
            {
                "persona_id": p.persona_id,
                "persona_name": p.persona_name,
                "persona_profile": p.persona_profile,
                "role": p.role,
                "engine": p.engine,
            }
            for p in r.participants
        ],
        "utterances": utterances,
    }


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

    async def list_by_simulation(self, simulation_id: str) -> list[dict]:
        """시뮬의 토론 목록(메타) — 최신순. 발언 제외, 카드 표시용."""
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(PersonaDebate)
                        .where(PersonaDebate.simulation_id == _as_uuid(simulation_id))
                        .order_by(PersonaDebate.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [_debate_meta(r) for r in rows]

    async def get_detail(self, debate_id: str) -> dict | None:
        """토론 상세 — participants·utterances 포함(채팅·결과 복원용). 없으면 None."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(PersonaDebate)
                    .where(PersonaDebate.id == _as_uuid(debate_id))
                    .options(
                        selectinload(PersonaDebate.participants),
                        selectinload(PersonaDebate.utterances),
                    )
                )
            ).scalar_one_or_none()
            return _debate_detail(row) if row is not None else None
