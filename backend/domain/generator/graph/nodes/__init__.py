"""파이프라인 노드 공통 — 진행률 emit 헬퍼."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig


def emit_progress(config: RunnableConfig, stage: str, pct: int, message: str) -> None:
    """SSE 진행률 콜백 호출 — service가 config["configurable"]["emit"]로 주입. 없으면 무시."""
    emit = (config.get("configurable") or {}).get("emit")
    if emit is not None:
        emit({"event": "progress", "stage": stage, "pct": pct, "message": message})
