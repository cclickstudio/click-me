# 매니지먼트 처방 선택(decide_action) eval을 LangSmith Dataset/Experiment로 올려 회귀를 추적한다.
# 실행: cd backend && uv run python -m domain.management.evals.langsmith_action_eval
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("LANGSMITH_API_KEY", os.environ.get("LANGCHAIN_API_KEY", ""))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langsmith import Client, evaluate  # noqa: E402 — load_dotenv 이후 임포트

from domain.management.agents.regeneration import RiskAppetite, decide_action  # noqa: E402
from domain.management.contracts.schemas import DiagnosisResult  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "regeneration" / "diagnosis_cases_v1.json"
DATASET_NAME = "management-action-selection"
FIXTURE_VERSION = "v1"


def _labeled_cases() -> list[dict]:
    """expected_action 라벨이 있는 케이스만 — 처방 선택 채점 대상."""
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [c for c in cases if "expected_action" in c]


def sync_dataset(client: Client) -> str:
    """픽스처를 LangSmith 데이터셋으로 동기화 — 없으면 생성, 있으면 예시 갱신."""
    cases = _labeled_cases()
    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        old = list(client.list_examples(dataset_id=ds.id))
        if old:
            client.delete_examples(example_ids=[e.id for e in old])
    else:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="매니지먼트 처방 선택 정확도 — 진단(DiagnosisResult)+의향 → action_type",
        )
    client.create_examples(
        dataset_id=ds.id,
        examples=[
            {
                "inputs": {
                    "diagnosis": c["diagnosis"],
                    "risk_appetite": c.get("risk_appetite", "conservative"),
                },
                "outputs": {"expected_action": c["expected_action"]},
                "metadata": {"case_id": c["case_id"], "fixture_version": FIXTURE_VERSION},
            }
            for c in cases
        ],
    )
    print(f"데이터셋 '{DATASET_NAME}' 동기화 — 예시 {len(cases)}개")
    return DATASET_NAME


def target(inputs: dict) -> dict:
    """진단+의향을 결정 코어에 넣어 처방을 고른다 — 실험 대상 시스템."""
    diagnosis = DiagnosisResult.model_validate(inputs["diagnosis"])
    risk = RiskAppetite(inputs.get("risk_appetite", "conservative"))
    return {"action": decide_action(diagnosis, risk)}


def action_match(run, example) -> dict:
    """선택한 처방이 기대 처방과 일치하면 1, 아니면 0."""
    chosen = (run.outputs or {}).get("action")
    expected = (example.outputs or {}).get("expected_action")
    return {"key": "action_match", "score": int(chosen == expected)}


def main() -> None:
    client = Client()
    sync_dataset(client)
    results = evaluate(
        target,
        data=DATASET_NAME,
        evaluators=[action_match],
        experiment_prefix="action-selection",
        metadata={"fixture_version": FIXTURE_VERSION},
        client=client,
    )
    print(results)


if __name__ == "__main__":
    main()
