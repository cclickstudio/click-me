# Mock 토론 엔진 — 실 LLM 없이 결정론 발화/판정 생성(라운드 골격 검증용)
#
# DebaterPort·JudgePort를 구현. 발화 text는 실제 반응(utterance) 재사용, 입장은 stance_score 기반.
# 실 LLM 엔진(Haiku/GPT/Gemini/Opus)으로 교체는 wiring에서만. mock은 재현·무비용.
from __future__ import annotations

from domain.simulation.contracts.debate_schemas import (
    DebateParticipant,
    DebateTopic,
    JudgeFinal,
    ParticipantDebate,
    RankedAction,
    Stance,
    Utterance,
)
from domain.simulation.contracts.schemas import PersonaReaction

# 주신호별 잠정 액션(결정론) — 실 Judge LLM이 대체할 placeholder.
_ACTIONS_BY_SIGNAL: dict[str, list[str]] = {
    "rejection": ["거부 사유(과장·불신) 완화 카피로 교체"],
    "trust_action_gap": ["한정·즉시성 메시지로 클릭 동기 부여", "행동 유도(CTA) 강화"],
    "early_attrition": ["초반 3초 후킹 강화"],
    "mid_attrition": ["다음 단계 진입 이유(혜택) 명시"],
}
_REASON_BY_ROLE: dict[str, str] = {
    "피벗": "신뢰는 있으나 즉시 행동 동기 부재",
    "완주자": "끝까지 반응할 만큼 동기가 충분",
    "비판자": "메시지 자체를 수용하지 않음",
    "미온": "관심은 있으나 움직일 이유 부족",
    "도메인 전문가(제품·카테고리)": "카테고리 관점에서 제품 가치 전달이 약함",
    "도메인 전문가(시장·유통)": "경쟁 제품 대비 차별점이 불명확",
    "마케팅 전문가(퍼포먼스)": "클릭 동기·CTA 설계가 부족",
    "마케팅 전문가(브랜드)": "메시지·포지셔닝이 모호",
}


def _stance_of(score: float) -> Stance:
    """입장 점수 → 라운드 stance(mock은 라운드 무관 동일 → churn 0 → 게이트가 MIN에서 종료)."""
    if score > 0.5:
        return "positive"
    if score < -0.5:
        return "negative"
    return "neutral"


class MockDebater:
    """결정론 토론자 — 반응(utterance) 재사용 + 역할/주신호 기반 reason·lever."""

    def __init__(self, reactions: list[PersonaReaction]) -> None:
        self._by_id = {r.persona_id: r for r in reactions}

    def speak(
        self, participant: DebateParticipant, round_n: int, phase: str, topic: DebateTopic
    ) -> Utterance:
        r = self._by_id.get(participant.persona_id)
        base = (r.utterance if r and r.utterance else f"{participant.role}로서의 반응") or ""
        lever = (_ACTIONS_BY_SIGNAL.get(topic.primary_signal) or ["메시지·CTA 보강"])[0]
        return Utterance(
            round=round_n,
            phase=phase,
            stance=_stance_of(participant.stance_score),
            text=f"[{phase}] {base}",
            reason=_REASON_BY_ROLE.get(participant.role, "역할 기반 반응"),
            lever=lever,
        )

    def answer_question(
        self,
        participant: DebateParticipant,
        question: str,
        topic: DebateTopic,
        history: list[Utterance],
    ) -> Utterance:
        """Q&A 답변(결정론·무비용) — 반응(utterance) 재사용. 실 구현은 Q&A 트랙(T2)."""
        r = self._by_id.get(participant.persona_id)
        base = (r.utterance if r and r.utterance else f"{participant.role}로서의 반응") or ""
        return Utterance(
            round=0,
            phase="질의응답",
            stance=_stance_of(participant.stance_score),
            text=f"[질의응답] {base}",
            reason=_REASON_BY_ROLE.get(participant.role, "역할 기반 반응"),
            lever="",
        )


class MockJudge:
    """결정론 Judge — 주제는 시드 그대로(재현)·라운드 정리(입장 집계)·주신호 기반 액션·최종 결론."""

    def refine_topic(self, topic: DebateTopic, digest: str) -> DebateTopic:
        return topic  # mock은 결정론 시드 주제 유지(무비용·재현). 유동 주제는 실 LLM만.

    def summarize_round(self, round_n: int, utterances: list[Utterance]) -> str:
        pos = sum(1 for u in utterances if u.stance == "positive")
        neu = sum(1 for u in utterances if u.stance == "neutral")
        neg = sum(1 for u in utterances if u.stance == "negative")
        return f"R{round_n}: 긍정 {pos}·중립 {neu}·부정 {neg}"

    def propose_actions(
        self, topic: DebateTopic, participants: list[ParticipantDebate]
    ) -> list[str]:
        return list(_ACTIONS_BY_SIGNAL.get(topic.primary_signal, ["메시지·CTA 보강"]))

    def finalize(self, topic: DebateTopic, participants: list[ParticipantDebate]) -> JudgeFinal:
        actions = self.propose_actions(topic, participants)
        # 마지막 라운드에서 긍정 입장이었던 사람을 개선안 지지자로(이름)
        supporters = [
            p.persona_name
            for p in participants
            if p.utterances and p.utterances[-1].stance == "positive"
        ]
        # 비판자가 마지막 발언이 negative일 때만 이견으로 — 좋은 광고면 비판자도 중립이라 제외.
        dissent = [
            f"{p.persona_name}(비판자): 어떤 액션에도 무반응 가능 — 타깃 밖 가능성"
            for p in participants
            if p.role == "비판자" and p.utterances and p.utterances[-1].stance == "negative"
        ]
        ranked = [
            RankedAction(
                rank=i + 1,
                action=a,
                expected_effect="병목 구간 전환 개선(추정)",
                supporting_personas=supporters,
            )
            for i, a in enumerate(actions)
        ]
        # 비전문가용 — mock은 결정론이라 주제·첫 액션을 쉬운 말 한두 문장으로 조합(실 LLM이 대체).
        first = actions[0] if actions else "메시지·CTA 보강"
        plain_summary = (
            f"쉽게 말하면, {topic.diagnosis} 지금으로선 '{first}'부터 해보는 게 좋겠습니다."
        )
        return JudgeFinal(
            headline=topic.diagnosis,
            plain_summary=plain_summary,
            consensus=[topic.question],
            dissent=dissent,
            ranked_actions=ranked,
        )
