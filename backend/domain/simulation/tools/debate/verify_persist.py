# 토론 영속화 검증 — ORM 메타데이터 + DebateResult→DB행 매핑(결정론). 실 DB 저장은 NeonDB 적용 후.
#
# 실행: cd backend && uv run python -m domain.simulation.tools.debate.verify_persist
# 검사: ① ORM 3테이블 등록 ② build_debate_rows 행 수·구조 ③ 매핑 결정론
# (SQLite는 JSONB/UUID 비호환이라 실제 save는 검증 제외 — alembic upgrade 후 운영 경로에서 확인)
from __future__ import annotations

import sys

from core.db import Base
from core.models import (  # noqa: F401
    PersonaDebate,
    PersonaDebateParticipant,
    PersonaDebateUtterance,
)
from domain.simulation.adapters.mock_debate import MockDebater, MockJudge
from domain.simulation.contracts.debate_schemas import DebateResult
from domain.simulation.repositories.debate_repository import build_debate_rows
from domain.simulation.tools.debate.analyzer import analyze_reactions
from domain.simulation.tools.debate.assigner import assign_panel
from domain.simulation.tools.debate.kpi import build_topic, compute_kpi
from domain.simulation.tools.debate.loader import load_all_dummies
from domain.simulation.tools.debate.runner import run_debate
from domain.simulation.tools.debate.selector import select_panel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_TABLES = ["persona_debates", "persona_debate_participants", "persona_debate_utterances"]


def _check(cond: bool, msg: str) -> bool:
    print(f"  [{'OK ' if cond else 'FAIL'}] {msg}")
    return cond


def _run_debate_for_dummy(d) -> DebateResult:
    """더미 → 8·9·10-a·10-b·10-c(mock) → DebateResult (검증용 결정론 조합)."""
    analysis = analyze_reactions(d.reactions)
    agg = compute_kpi(d.reactions)
    topic = build_topic(analysis, agg, d.ad_analysis)
    panel = assign_panel(select_panel(d.reactions))
    return run_debate(panel, topic, MockDebater(d.reactions), MockJudge())


def main() -> int:
    all_ok = True

    # ① ORM 3테이블이 Base.metadata에 등록됐는지
    print("=== ORM 메타데이터 ===")
    for t in _TABLES:
        all_ok &= _check(t in Base.metadata.tables, f"테이블 등록: {t}")
    print()

    dummies = load_all_dummies()
    for d in dummies:
        debate = _run_debate_for_dummy(d)
        drow, prows, urows = build_debate_rows("00000000-0000-0000-0000-000000000001", debate)
        print(f"=== {d.name} ===")
        print(f"  rows: debate=1 participants={len(prows)} utterances={len(urows)}")

        ok_a = _check(
            len(prows) == len(debate.participants) and len(prows) == min(6, len(d.reactions)),
            f"participant 행 {len(prows)}",
        )
        expected_utt = sum(len(p.utterances) for p in debate.participants)
        ok_b = _check(len(urows) == expected_utt, f"utterance 행 {len(urows)} == {expected_utt}")
        ok_c = _check(
            isinstance(drow["engines"], list)
            and isinstance(drow["judge_log"], dict)
            and (drow["final"] is None or isinstance(drow["final"], dict))
            and drow["status"] == "COMPLETED",
            "debate_row JSONB 타입(engines list·judge_log dict·final dict)",
        )
        # 결정론
        debate2 = _run_debate_for_dummy(d)
        rows2 = build_debate_rows("00000000-0000-0000-0000-000000000001", debate2)
        ok_d = _check((drow, prows, urows) == rows2, "매핑 결정론")

        all_ok = all_ok and ok_a and ok_b and ok_c and ok_d
        print()

    print("전체 통과 [PASS]" if all_ok else "실패 있음 [FAIL]")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
