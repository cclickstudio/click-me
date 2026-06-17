# stream 골격 검증 — DebateService를 더미로 구동해 이벤트 시퀀스·결과·결정론 확인(도메인 내부)
#
# 실행: cd backend && uv run python -m domain.simulation.tools.debate.verify_stream
# 검사: ① 단계 이벤트 순서 ② result 키·패널 ③ 10-c/11 placeholder(pending·None) ④ 결정론
from __future__ import annotations

import asyncio
import sys

from domain.simulation.adapters.memory_store import InMemorySimulationStore
from domain.simulation.service.debate_service import DebateService
from domain.simulation.tools.debate.loader import load_all_dummies

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 7번 이후 결정론 파이프라인의 기대 단계 순서.
EXPECTED_STAGES = ["analysis", "kpi", "topic", "selection", "assignment", "debate", "report"]


def _check(cond: bool, msg: str) -> bool:
    print(f"  [{'OK ' if cond else 'FAIL'}] {msg}")
    return cond


def _strip_run_id(result: dict) -> dict:
    """결정론 비교용 — run_id(uuid)만 제외하고 나머지 산출을 비교."""
    return {k: v for k, v in result.items() if k != "run_id"}


async def main() -> int:
    dummies = load_all_dummies()
    print(f"로드된 더미: {len(dummies)}개\n")
    all_ok = True

    for d in dummies:
        store = InMemorySimulationStore()
        svc = DebateService(store=store)
        result = await svc.run(d.reactions, d.ad_analysis)
        run_id = result["run_id"]
        events = store.get_events(run_id)
        stages = [e.get("stage") for e in events if e.get("event") == "progress"]
        last = events[-1]

        print(f"=== {d.name} ===")
        print(f"  stages: {stages}")
        print(f"  completed: {last.get('event')} pct={last.get('pct')}")

        # ① 단계 순서
        ok1 = _check(stages == EXPECTED_STAGES, f"단계 순서 == {EXPECTED_STAGES}")
        # ② result 키 + 패널
        keys_ok = all(k in result for k in ("analysis", "aggregate", "topic", "panel"))
        panel_n = len(result["panel"]["participants"]) if result.get("panel") else 0
        ok2 = _check(keys_ok and panel_n == min(8, len(d.reactions)), f"result 키·패널 {panel_n}명")
        # ③ 엔진 미주입 — 토론(10-c)은 None, 리포트(11)는 조립됨(debate_available=False) + completed
        report = result.get("report")
        ok3 = _check(
            result["debate"] is None
            and report is not None
            and report["debate_available"] is False
            and last["event"] == "completed",
            "10-c None + 리포트(debate_available=False) + completed",
        )
        # ④ 결정론(run_id 제외 동일)
        store2 = InMemorySimulationStore()
        result2 = await DebateService(store=store2).run(d.reactions, d.ad_analysis)
        ok4 = _check(_strip_run_id(result) == _strip_run_id(result2), "결정론(run_id 제외 동일)")

        all_ok = all_ok and ok1 and ok2 and ok3 and ok4
        print()

    print("전체 통과 [PASS]" if all_ok else "실패 있음 [FAIL]")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
