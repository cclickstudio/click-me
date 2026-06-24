# 매니지먼트 진단 정확도 eval(고장주입 정답 대비 + 오탐률 게이트#5)을 LangSmith Experiment로 올린다.
# 실행: cd backend && uv run python -m domain.management.evals.langsmith_diagnosis_eval
from __future__ import annotations

import os
import sys

os.environ["USE_MOCK"] = "true"  # 고장주입 eval은 hermetic — 실 Meta·키 무관 (게이트 #9)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()
os.environ.setdefault("LANGSMITH_API_KEY", os.environ.get("LANGCHAIN_API_KEY", ""))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langsmith import Client, evaluate  # noqa: E402

from domain.management.contracts.fault_injection import FaultConfig, FaultMode  # noqa: E402
from domain.management.detection.guardrails import GuardVerdict  # noqa: E402
from domain.management.detection.service.detection_service import (  # noqa: E402
    run_detection_for_fault,
)
from domain.management.evals.diagnosis_eval import FAULT_TO_LABEL  # noqa: E402

DATASET_NAME = "management-diagnosis"
SEEDS = range(10)  # seed × fault(5) = 50 고장 케이스 + 10 정상(오탐) 케이스 = 60


def _example_rows() -> list[dict]:
    """고장 케이스(정답=주입 anomaly) + 정상 케이스(정답='none', 오탐 채점용)."""
    rows: list[dict] = []
    for seed in SEEDS:
        for mode, expected in FAULT_TO_LABEL.items():
            rows.append(
                {
                    "inputs": {"fault_mode": mode.value, "seed": seed},
                    "outputs": {"expected": expected.value},
                    "metadata": {"kind": "fault"},
                }
            )
        rows.append(
            {
                "inputs": {"fault_mode": None, "seed": seed},
                "outputs": {"expected": "none"},
                "metadata": {"kind": "clean"},
            }
        )
    return rows


def sync_dataset(client: Client) -> str:
    rows = _example_rows()
    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        old = list(client.list_examples(dataset_id=ds.id))
        if old:
            client.delete_examples(example_ids=[e.id for e in old])
    else:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="매니지먼트 진단 정확도 — 주입 고장 대비 판정 + 오탐률(게이트#5)",
        )
    client.create_examples(dataset_id=ds.id, examples=rows)
    print(f"데이터셋 '{DATASET_NAME}' 동기화 — 예시 {len(rows)}개")
    return DATASET_NAME


def target(inputs: dict) -> dict:
    """주입 고장(또는 정상)으로 detection을 돌려 판정 anomaly를 관측한다."""
    mode = inputs.get("fault_mode")
    seed = inputs["seed"]
    if mode:
        dx, _ = run_detection_for_fault(FaultConfig(mode=FaultMode(mode)), seed=seed)
        predicted = dx.anomaly_type.value if dx else "none"
    else:
        _, guard = run_detection_for_fault(None, seed=seed)
        predicted = "delivery_anomaly_fp" if guard == GuardVerdict.DELIVERY_ANOMALY else "none"
    return {"predicted": predicted}


def correct(run, example) -> dict:
    """판정이 정답과 일치하면 1 — 정상 케이스는 'none' 유지가 정답(오탐이면 0)."""
    predicted = (run.outputs or {}).get("predicted")
    expected = (example.outputs or {}).get("expected")
    return {"key": "correct", "score": int(predicted == expected)}


def false_positive_rate(runs, examples) -> dict:
    """정상 케이스 중 이상으로 잘못 잡은 비율 — 게이트#5(≤5%) 추적."""
    clean = [
        (r, e)
        for r, e in zip(runs, examples, strict=False)
        if (e.outputs or {}).get("expected") == "none"
    ]
    if not clean:
        return {"key": "false_positive_rate", "score": 0.0}
    fp = sum(1 for r, _ in clean if (r.outputs or {}).get("predicted") != "none")
    return {"key": "false_positive_rate", "score": fp / len(clean)}


def main() -> None:
    client = Client()
    sync_dataset(client)
    results = evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[correct],
        summary_evaluators=[false_positive_rate],
        experiment_prefix="diagnosis",
        client=client,
    )
    print(results)


if __name__ == "__main__":
    main()
