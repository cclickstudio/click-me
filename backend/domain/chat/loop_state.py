# 개선 루프 상태 — 시뮬↔제너 왕복(최대 3회) HITL 컨트롤러의 세션별 인메모리 상태
"""시뮬 결과가 약하면 개선 시안 생성을 제안(approval)하고, 수락 시 왕복을 1회 카운트한다.
서버 프로세스 메모리에만 보관(재시작 시 초기화). 오케스트레이터와 /approve 라우터가 공유.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MAX_LOOP = 3  # 시뮬↔제너 왕복 최대 횟수


@dataclass
class LoopState:
    loop_count: int = 0  # 최대 MAX_LOOP
    phase: str = "idle"  # idle | sim_done | gen_done | finished
    last_sim_id: str | None = None
    last_gen_id: str | None = None
    weak_reasons: list[str] = field(default_factory=list)


_store: dict[str, LoopState] = {}


def _key(session_id: str | None) -> str:
    return session_id or "__ephemeral__"


def get_loop_state(session_id: str | None) -> LoopState:
    key = _key(session_id)
    st = _store.get(key)
    if st is None:
        st = LoopState()
        _store[key] = st
    return st


def reset_loop_state(session_id: str | None) -> None:
    _store.pop(_key(session_id), None)
