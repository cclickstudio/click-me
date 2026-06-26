# 챗 전용 시뮬레이션 서비스 싱글톤 — 챗 트리거 런의 진행/결과를 챗 라우터가 같은 인스턴스로 노출.
"""챗에서 띄운 시뮬은 이 단일 인스턴스(인메모리 store 공유)에서 돌아간다.

표준 시뮬 라우터(api/routers/simulation)의 싱글톤과 분리 — 챗 런은 챗 라우터의
/api/chat/sim/{run_id}/stream·/result로 진행/결과를 본다(시뮬 도메인 무수정, 경계 보존).
get_chat_sim_service는 build_simulation_service(시뮬 wiring)로 인스턴스를 1회 만든다.
"""

from __future__ import annotations

from typing import Any

_state: dict[str, Any] = {}


def get_chat_sim_service(settings) -> Any:
    """챗 트리거 시뮬을 돌리고 진행/결과를 보관하는 단일 인스턴스(인메모리 store 공유)."""
    if "svc" not in _state:
        from domain.simulation.wiring import build_simulation_service  # noqa: PLC0415

        _state["svc"] = build_simulation_service(settings)
    return _state["svc"]


def get_chat_debate_service(settings) -> Any:
    """챗 트리거 토론을 돌리고 진행/결과를 보관하는 단일 인스턴스(인메모리 store 공유)."""
    if "debate_svc" not in _state:
        from domain.simulation.wiring import build_debate_service  # noqa: PLC0415

        _state["debate_svc"] = build_debate_service(settings)
    return _state["debate_svc"]


def set_last_run_id(run_id: str) -> None:
    """가장 최근 챗 트리거 run_id 기록 — '방금 시뮬 다 됐어?'의 기본 대상(프로세스 스코프)."""
    _state["last_run_id"] = run_id


def get_last_run_id() -> str | None:
    """최근 챗 트리거 run_id(없으면 None). 멀티유저 환경에선 명시 run_id 우선."""
    return _state.get("last_run_id")
