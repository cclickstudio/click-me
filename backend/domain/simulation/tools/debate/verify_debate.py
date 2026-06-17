# 10-c mock 토론 검증 — 라운드 게이트 단위 케이스 + mock 엔진 토론 구조·결정론(도메인 내부)
#
# 실행: cd backend && uv run python -m domain.simulation.tools.debate.verify_debate
# 검사: ① should_continue/stop_reason 게이트 ② mock 토론 라운드·발언 구조 ③ 결정론 ④ stream 단계
from __future__ import annotations

import asyncio
import sys

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.adapters.mock_debate import MockDebater, MockJudge
from domain.simulation.service.debate_service import DebateService
from domain.simulation.tools.debate.loader import load_all_dummies
from domain.simulation.tools.debate.runner import should_continue, stop_reason_for

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _check(cond: bool, msg: str) -> bool:
    print(f"  [{'OK ' if cond else 'FAIL'}] {msg}")
    return cond


def _gate_cases() -> bool:
    """유동 게이트 단위 — 최소 전 진행 / 정착 종료 / 변동 지속 / 상한 종료."""
    print("=== 게이트 단위 케이스 ===")
    ok = True
    ok &= _check(should_continue(1, 0, 0.0) is True, "round<MIN → 계속")
    ok &= _check(should_continue(2, 0, 0.0) is False, "churn 낮음 → 종료")
    ok &= _check(should_continue(2, 3, 2.0) is True, "churn 높음 → 계속")
    ok &= _check(should_continue(4, 3, 2.0) is False, "round>=MAX → 종료")
    ok &= _check(stop_reason_for(2, 0, 0.0) == "consensus", "정착+합의 → consensus")
    ok &= _check(stop_reason_for(2, 0, 2.0) == "dissensus", "정착+이견 → dissensus")
    ok &= _check(stop_reason_for(4, 3, 2.0) == "max", "상한 → max")
    print()
    return bool(ok)


async def _debate_cases() -> bool:
    dummies = load_all_dummies()
    all_ok = True
    for d in dummies:
        store = InMemorySimulationStore()
        svc = DebateService(
            store=store, debater_factory=lambda rs: MockDebater(rs), judge=MockJudge()
        )
        result = await svc.run(d.reactions, d.ad_analysis)
        debate = result["debate"]
        events = store.get_events(result["run_id"])
        stages = [e.get("stage") for e in events if e.get("event") == "progress"]

        print(f"=== {d.name} ===")
        print(f"  stages: {stages}")
        rr = debate["rounds_run"]
        print(
            f"  rounds_run={rr} stop_reason={debate['stop_reason']} "
            f"actions={len(debate['final']['ranked_actions'])}"
        )

        ok_a = _check(debate is not None and 2 <= rr <= 4, f"rounds_run {rr} ∈ [2,4]")
        ok_b = _check(
            debate["stop_reason"] in ("consensus", "dissensus", "max"),
            f"stop_reason {debate['stop_reason']}",
        )
        # 각 참가자 발언 수 == rounds_run
        utt_ok = all(len(p["utterances"]) == rr for p in debate["participants"])
        ok_c = _check(
            utt_ok and len(debate["participants"]) == min(8, len(d.reactions)),
            "참가자 8명·발언수==rounds_run",
        )
        ok_d = _check(len(debate["final"]["ranked_actions"]) >= 1, "Judge 개선안 ≥1")
        # 실시간 stream — 발언(utterance) emit 수 == 전체 발언 수, round_summary·judge_final 존재
        utt_events = sum(1 for s in stages if s == "utterance")
        total_utt = sum(len(p["utterances"]) for p in debate["participants"])
        ok_e = _check(
            utt_events == total_utt and "round_summary" in stages and "judge_final" in stages,
            f"stream 발언 {utt_events}건·round_summary·judge_final",
        )
        # 조각 11 리포트 — 토론 있을 때 debate_available·인용·개선안 매핑
        report = result["report"]
        ok_g = _check(
            report is not None
            and report["debate_available"] is True
            and len(report["quotes"]) == len(debate["participants"])
            and report["ranked_actions"] == debate["final"]["ranked_actions"]
            and report["headline"] == debate["final"]["headline"],
            f"리포트 조립(인용 {len(report['quotes'])}·개선안 {len(report['ranked_actions'])})",
        )
        # 결정론
        store2 = InMemorySimulationStore()
        svc2 = DebateService(
            store=store2, debater_factory=lambda rs: MockDebater(rs), judge=MockJudge()
        )
        result2 = await svc2.run(d.reactions, d.ad_analysis)
        ok_f = _check(
            result2["debate"] == debate and result2["report"] == report,
            "결정론(토론·리포트 산출 동일)",
        )

        all_ok = all_ok and ok_a and ok_b and ok_c and ok_d and ok_e and ok_f and ok_g
        print()
    return all_ok


async def main() -> int:
    gate_ok = _gate_cases()
    debate_ok = await _debate_cases()
    all_ok = gate_ok and debate_ok
    print("전체 통과 [PASS]" if all_ok else "실패 있음 [FAIL]")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
