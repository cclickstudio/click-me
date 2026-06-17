# 선발 함정 테스트 채점기 — selection-traps.json으로 결정론 vs LLM 게이트 정답률을 비교
#
# 각 case의 reactions로 select_panel(lay_count=4)을 돌려, 해당 role 슬롯에 뽑힌 persona_id가
# expected_pick과 같은지 비교한다. 스칼라가 완전 동률인 함정이라 결정론은 id순으로 trap_distractor를
# 찍어 틀린다 → LLM 게이트(동점일 때만 텍스트로 재판단)가 그걸 바로잡는지 숫자로 확인.
# 실행: cd backend && uv run python -m domain.simulation.tools.debate.trap_check         (결정론만)
#       cd backend && uv run python -m domain.simulation.tools.debate.trap_check --llm   (LLM 비교)
from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from domain.simulation.contracts.schemas import PersonaReaction
from domain.simulation.tools.debate.selector import RerankFn, select_panel

_TRAPS = Path(__file__).resolve().parents[2] / "dummy" / "selection-traps.json"


def _score(cases: list[dict], rerank_fn: RerankFn | None, label: str) -> int:
    correct = 0
    print(f"== {label} ==")
    for c in cases:
        reactions = [PersonaReaction.model_validate(r) for r in c["reactions"]]
        panel = select_panel(reactions, lay_count=4, rerank_fn=rerank_fn)
        picked = next((p.persona_id for p in panel.participants if p.role == c["role"]), None)
        ok = picked == c["expected_pick"]
        correct += ok
        mark = "정답" if ok else "함정에 걸림"
        trap = " (=trap_distractor)" if picked == c["trap_distractor"] else ""
        print(
            f"  [{c['case_id']}] {c['role']}: "
            f"정답={c['expected_pick']} / 선택={picked}{trap} -> {mark}"
        )
    print(f"  => {label} 정답률: {correct}/{len(cases)}\n")
    return correct


def run(use_llm: bool = False) -> int:
    cases = json.loads(_TRAPS.read_text(encoding="utf-8"))["cases"]
    print(f"선발 함정 테스트 ({len(cases)}케이스, 4역할)\n")

    det = _score(cases, None, "결정론 베이스라인")
    if not use_llm:
        print("(--llm 인자를 주면 LLM 게이트와 정확도를 비교합니다.)")
        return det

    from domain.simulation.adapters.llm_selector import LLMSelector
    from domain.simulation.wiring import _ensure_env

    _ensure_env("ANTHROPIC_API_KEY")  # trap_check는 wiring을 안 거치므로 .env를 직접 적재
    rerank: Callable[..., str] = LLMSelector().choose
    llm = _score(cases, rerank, "LLM 게이트(Sonnet, 3표 다수결)")
    print(
        f"정확도 변화(결정론 -> LLM 게이트): "
        f"{det}/{len(cases)} -> {llm}/{len(cases)}  (증감 {llm - det:+d})"
    )
    return llm


if __name__ == "__main__":
    run(use_llm="--llm" in sys.argv)
