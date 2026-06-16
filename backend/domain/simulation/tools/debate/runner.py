# 조각 10-c 라운드 러너 — 유동 라운드(2~4) 토론 진행. 발화는 포트(엔진), 게이트는 결정론.
#
# 라운드마다 역할(동사) 다름: R1[발산] R2[반박] R3[검증]. Judge가 라운드 정리 → 최종 결론.
# 멈춤은 느낌이 아니라 숫자(churn·dispersion)로 — MIN 2 / MAX 4. 상세: persona-debate-pipeline.md ④
from __future__ import annotations

from statistics import pstdev

from domain.simulation.contracts.debate_ports import DebaterPort, JudgePort
from domain.simulation.contracts.debate_schemas import (
    AssignedPanel,
    DebateResult,
    DebateTopic,
    ParticipantDebate,
)

MIN_ROUNDS, MAX_ROUNDS = 2, 4  # 최소 2(발산+반박) / 최대 4(비용 상한·종료 보장)
CHURN_TH, DISP_TH = 1, 1.5  # 변동 1명 이하 = 정착 / 분산 1.5 이하 = 합의

_STANCE_VAL = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
_PHASE = {1: "발산", 2: "반박", 3: "검증"}


def phase_for(round_n: int) -> str:
    """라운드 동사 — 4라운드째도 검증(추가 검증)."""
    return _PHASE.get(round_n, "검증")


def should_continue(round_n: int, churn: int, dispersion: float) -> bool:
    """3갈래 게이트 — 최소 전엔 진행, 상한이면 종료, 안 움직이면(churn 낮음) 종료."""
    if round_n < MIN_ROUNDS:
        return True
    if round_n >= MAX_ROUNDS:
        return False
    return churn > CHURN_TH  # 아직 움직이면 한 라운드 더, 정착했으면 종료


def stop_reason_for(round_n: int, churn: int, dispersion: float) -> str:
    """종료 사유 — 상한 우선(max), 그 외엔 분산으로 합의/이견 구분."""
    if round_n >= MAX_ROUNDS:
        return "max"
    if dispersion <= DISP_TH:
        return "consensus"  # 정착 + 합의
    return "dissensus"  # 정착 + 굳은 이견


def run_debate(
    panel: AssignedPanel, topic: DebateTopic, debater: DebaterPort, judge: JudgePort
) -> DebateResult:
    """유동 라운드 토론 — 포트로 발화 수집, 결정론 게이트로 종료 판단, Judge로 결론."""
    order = panel.participants  # slot 순
    pdebates: dict[str, ParticipantDebate] = {
        p.persona_id: ParticipantDebate(
            persona_id=p.persona_id,
            persona_name=p.persona_name,
            persona_profile=p.persona_profile,
            role=p.role,
            engine=p.engine,
            utterances=[],
        )
        for p in order
    }

    round_summaries: dict[int, str] = {}
    prev_stances: dict[str, str] = {}
    rounds_run = 0
    stop_reason = "max"

    for round_n in range(1, MAX_ROUNDS + 1):
        phase = phase_for(round_n)
        cur_stances: dict[str, str] = {}
        round_utts = []
        for p in order:
            u = debater.speak(p, round_n, phase, topic)
            pdebates[p.persona_id].utterances.append(u)
            round_utts.append(u)
            cur_stances[p.persona_id] = u.stance
        round_summaries[round_n] = judge.summarize_round(round_n, round_utts)
        rounds_run = round_n

        # churn = 직전 라운드 대비 입장 바꾼 사람 수 / dispersion = 이번 라운드 입장 퍼짐
        churn = sum(1 for pid, s in cur_stances.items() if prev_stances.get(pid, s) != s)
        vals = [_STANCE_VAL[s] for s in cur_stances.values()]
        dispersion = pstdev(vals) if len(vals) > 1 else 0.0
        prev_stances = cur_stances

        if not should_continue(round_n, churn, dispersion):
            stop_reason = stop_reason_for(round_n, churn, dispersion)
            break

    participants = [pdebates[p.persona_id] for p in order]
    proposed_actions = judge.propose_actions(topic, participants)
    final = judge.finalize(topic, participants)
    models = {
        "judge": panel.judge_engine,
        "engines": sorted({p.engine for p in panel.participants}),
    }

    return DebateResult(
        topic=topic.headline,
        rounds_run=rounds_run,
        stop_reason=stop_reason,
        models=models,
        participants=participants,
        round_summaries=round_summaries,
        proposed_actions=proposed_actions,
        final=final,
    )
