# 토론(10-c) 포트 — 토론자·Judge 엔진의 계약(외부 의존 없음). mock↔실 LLM은 wiring에서 교체.
#
# runner는 이 포트에만 의존한다. mock 엔진(adapters)·실 LLM 엔진 모두 이 시그니처를 구현.
from __future__ import annotations

from typing import Protocol

from domain.simulation.contracts.debate_schemas import (
    DebateParticipant,
    DebateTopic,
    JudgeFinal,
    ParticipantDebate,
    Utterance,
)


class DebaterPort(Protocol):
    """토론자 엔진 — 한 참가자가 한 라운드에 발언 1건을 생성."""

    def speak(
        self, participant: DebateParticipant, round_n: int, phase: str, topic: DebateTopic
    ) -> Utterance: ...

    def answer_question(
        self,
        participant: DebateParticipant,
        question: str,
        topic: DebateTopic,
        history: list[Utterance],
    ) -> Utterance:
        """토론 종료 후 Q&A — 한 참가자가 사용자 질문에 답변 1건을 생성(phase='질의응답').

        history는 이 참가자가 토론에서 한 발언들(일관성 유지용). 본문 구현은 Q&A 트랙(T2).
        """
        ...


class JudgePort(Protocol):
    """주최자(Judge) 엔진 — 토론 주제 정련·라운드 정리·잠정 액션·최종 결론."""

    def refine_topic(self, topic: DebateTopic, digest: str) -> DebateTopic:
        """결정론 시드 주제를 데이터 기반 논쟁적 주제로 정련. mock은 시드 그대로(재현)."""
        ...

    def summarize_round(self, round_n: int, utterances: list[Utterance]) -> str: ...

    def propose_actions(
        self, topic: DebateTopic, participants: list[ParticipantDebate]
    ) -> list[str]: ...

    def finalize(self, topic: DebateTopic, participants: list[ParticipantDebate]) -> JudgeFinal: ...
