# 인메모리 SimulationStore — 실행 상태·SSE 이벤트·결과 보관 (DB 영속화는 추후)
from __future__ import annotations


class InMemorySimulationStore:
    """실행 상태·이벤트·결과 저장 — 프로세스 메모리. repositories/ DB 어댑터로 대체 예정."""

    def __init__(self) -> None:
        self._runs: dict[str, dict] = {}

    def create_run(self, run_id: str) -> None:
        self._runs[run_id] = {"status": "QUEUED", "events": [], "result": None}

    def emit(self, run_id: str, event: dict) -> None:
        self._runs[run_id]["events"].append(event)

    def set_status(self, run_id: str, status: str) -> None:
        self._runs[run_id]["status"] = status

    def set_result(self, run_id: str, result: dict) -> None:
        self._runs[run_id]["result"] = result

    def get_events(self, run_id: str) -> list[dict]:
        run = self._runs.get(run_id)
        return run["events"] if run else []

    def get_status(self, run_id: str) -> str | None:
        run = self._runs.get(run_id)
        return run["status"] if run else None

    def get_result(self, run_id: str) -> dict | None:
        run = self._runs.get(run_id)
        return run["result"] if run else None
