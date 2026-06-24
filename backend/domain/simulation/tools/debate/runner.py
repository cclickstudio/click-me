# 조각 10-c 라운드 러너 — 유동 라운드(2~4) 토론 진행. 발화는 포트(엔진), 게이트는 결정론.
#
# 라운드마다 역할(동사) 다름: R1[발산] R2[반박] R3[검증]. Judge가 라운드 정리 → 최종 결론.
# 멈춤은 느낌이 아니라 숫자(churn·dispersion)로 — MIN 2 / MAX 4. 상세: persona-debate-pipeline.md ④
from __future__ import annotations

from collections.abc import Callable
from statistics import pstdev

from domain.simulation.contracts.debate_ports import DebaterPort, JudgePort
from domain.simulation.contracts.debate_schemas import (
    AssignedPanel,
    DebateParticipant,
    DebateResult,
    DebateTopic,
    ParticipantDebate,
)

MIN_ROUNDS, MAX_ROUNDS = 2, 4  # 최소 2(발산+반박) / 최대 4(비용 상한·종료 보장)
CHURN_TH, DISP_TH = 1, 1.5  # 변동 1명 이하 = 정착 / 분산 1.5 이하 = 합의
# 진행률(SSE) — assignment(75) 후 judge_final(92) 사이를 토론 발언으로 채운다.
# 라운드 가변(2~4)이라 평균 3라운드를 예상치로 잡고 90을 상한으로 단조 증가(92와 충돌 방지).
PCT_START, PCT_CAP, EXPECTED_ROUNDS = 75, 90, 3

_STANCE_VAL = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
_PHASE = {1: "발산", 2: "반박", 3: "검증"}


def phase_for(round_n: int) -> str:
    """라운드 동사 — 4라운드째도 검증(추가 검증)."""
    return _PHASE.get(round_n, "검증")


def _order_by_stance(
    order: list[DebateParticipant], stances: dict[str, str]
) -> list[DebateParticipant]:
    """직전 입장 기준 긍정·부정 번갈아 배치(중립은 뒤) — 반박 라운드 대립 구도 노출.

    발언 순서(=SSE 표시 순서)만 바꾼다. 집계(churn·dispersion)는 persona_id 기반이라 무관.
    """
    pos = [p for p in order if stances.get(p.persona_id) == "positive"]
    neg = [p for p in order if stances.get(p.persona_id) == "negative"]
    neu = [p for p in order if stances.get(p.persona_id) not in ("positive", "negative")]
    woven = []
    i = j = 0
    while i < len(pos) or j < len(neg):
        if i < len(pos):
            woven.append(pos[i])
            i += 1
        if j < len(neg):
            woven.append(neg[j])
            j += 1
    return woven + neu


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
    panel: AssignedPanel,
    topic: DebateTopic,
    debater: DebaterPort,
    judge: JudgePort,
    on_event: Callable[[dict], None] | None = None,
) -> DebateResult:
    """유동 라운드 토론 — 포트로 발화 수집, 결정론 게이트로 종료 판단, Judge로 결론.

    on_event(주입 시): 발언 1건마다 utterance 이벤트, 라운드 끝마다 round_summary 이벤트를
    실시간으로 흘린다(SSE 토론 과정 노출). 스레드세이프(호출자가 store.emit append만 수행).
    """
    order = panel.participants  # slot 순

    def emit(ev: dict) -> None:
        if on_event is not None:
            on_event(ev)

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
    # 직전 라운드 발언 [(persona_id, name, stance, text)] — 다음 라운드 토론자의 반박 grounding.
    prev_utts: list[tuple[str, str, str, str]] | None = None
    rounds_run = 0
    stop_reason = "max"

    # 발언 1건마다 pct를 75→90으로 단조 증가(예상 = 참가자 × 평균 라운드).
    expected_utts = max(1, len(order) * EXPECTED_ROUNDS)
    spoken = 0
    pct = PCT_START

    for round_n in range(1, MAX_ROUNDS + 1):
        phase = phase_for(round_n)
        # R1은 slot 순(발산), 반박 라운드부터는 직전 입장 기준 긍·부 교차(대립 구도 노출).
        speak_order = order if round_n == 1 else _order_by_stance(order, prev_stances)
        cur_stances: dict[str, str] = {}
        round_utts = []
        round_prior: list[tuple[str, str, str, str]] = []
        for p in speak_order:
            u = debater.speak(p, round_n, phase, topic, prior=prev_utts)
            pdebates[p.persona_id].utterances.append(u)
            round_utts.append(u)
            round_prior.append((p.persona_id, p.persona_name, u.stance, u.text))
            cur_stances[p.persona_id] = u.stance
            spoken += 1
            pct = min(PCT_CAP, PCT_START + round(spoken / expected_utts * (PCT_CAP - PCT_START)))
            emit(
                {
                    "event": "progress",
                    "stage": "utterance",
                    "pct": pct,
                    "round": round_n,
                    "phase": phase,
                    "persona_id": p.persona_id,
                    "persona_name": p.persona_name,
                    "persona_profile": p.persona_profile,
                    "role": p.role,
                    "engine": p.engine,
                    "stance": u.stance,
                    "text": u.text,
                    "reason": u.reason,
                    "lever": u.lever,
                }
            )
        summary = judge.summarize_round(round_n, round_utts)
        round_summaries[round_n] = summary
        rounds_run = round_n
        emit(
            {
                "event": "progress",
                "stage": "round_summary",
                "pct": pct,
                "round": round_n,
                "summary": summary,
            }
        )

        # churn = 직전 라운드 대비 입장 바꾼 사람 수 / dispersion = 이번 라운드 입장 퍼짐
        churn = sum(1 for pid, s in cur_stances.items() if prev_stances.get(pid, s) != s)
        vals = [_STANCE_VAL[s] for s in cur_stances.values()]
        dispersion = pstdev(vals) if len(vals) > 1 else 0.0
        prev_stances = cur_stances
        prev_utts = round_prior  # 다음 라운드 토론자에게 줄 직전 발언(반박 grounding)

        if not should_continue(round_n, churn, dispersion):
            stop_reason = stop_reason_for(round_n, churn, dispersion)
            break

    participants = [pdebates[p.persona_id] for p in order]
    final = judge.finalize(topic, participants)
    # 잠정 액션은 최종 결론(ranked_actions)에 흡수 — 별도 Judge 호출 제거(비용 최적화).
    proposed_actions = [a.action for a in final.ranked_actions]
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
