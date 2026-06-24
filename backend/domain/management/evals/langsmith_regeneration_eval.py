# 매니지먼트 재생성 품질 eval(승률·가드레일·schema 준수)을 LangSmith Experiment로 올린다.
# 실행: cd backend && uv run python -m domain.management.evals.langsmith_regeneration_eval
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("LANGSMITH_API_KEY", os.environ.get("LANGCHAIN_API_KEY", ""))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langsmith import Client, aevaluate  # noqa: E402 — load_dotenv 이후 임포트

from domain.management.agents.regeneration import RemediationContext  # noqa: E402
from domain.management.agents.regeneration_tools import build_regeneration_agent  # noqa: E402
from domain.management.contracts.schemas import DiagnosisResult  # noqa: E402
from domain.management.evals.regeneration_eval import (  # noqa: E402
    _EVAL_CONTEXT_DEFAULTS,
    _score_proposal,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "regeneration" / "diagnosis_cases_v1.json"
DATASET_NAME = "management-regeneration"
FIXTURE_VERSION = "v1"

# 기본 tool 체인(생성·시뮬·미리보기) agent — 1회 빌드해 모든 케이스에 재사용.
_AGENT = build_regeneration_agent()


def _cases() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def sync_dataset(client: Client) -> str:
    """픽스처를 LangSmith 데이터셋으로 동기화 — 없으면 생성, 있으면 예시 갱신."""
    cases = _cases()
    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        old = list(client.list_examples(dataset_id=ds.id))
        if old:
            client.delete_examples(example_ids=[e.id for e in old])
    else:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="매니지먼트 재생성 품질 — 진단→제안 승률·가드레일·schema",
        )
    client.create_examples(
        dataset_id=ds.id,
        examples=[
            {
                "inputs": {"diagnosis": c["diagnosis"]},
                "outputs": {"baseline_score": c["baseline_score"]},
                "metadata": {"case_id": c["case_id"], "fixture_version": FIXTURE_VERSION},
            }
            for c in cases
        ],
    )
    print(f"데이터셋 '{DATASET_NAME}' 동기화 — 예시 {len(cases)}개")
    return DATASET_NAME


async def atarget(inputs: dict) -> dict:
    """진단을 재생성 agent에 넣어 제안을 만들고 후보 점수·가드·schema를 관측한다."""
    diagnosis = DiagnosisResult.model_validate(inputs["diagnosis"])
    context = RemediationContext(**_EVAL_CONTEXT_DEFAULTS)
    proposal = await _AGENT.propose(diagnosis, context)
    scores, guard_ok, valid = _score_proposal(proposal, banned_ids=set())
    return {
        "candidate_scores": list(scores),
        "best_score": max(scores) if scores else None,
        "guardrail_passed": guard_ok,
        "schema_valid": valid,
        "action": proposal.action_type if proposal else None,
    }


def win(run, example) -> dict:
    """최고 후보 점수 > 원본(baseline)이면 개선(승) — PRD §5.2 승률의 정의."""
    scores = (run.outputs or {}).get("candidate_scores") or []
    baseline = (example.outputs or {}).get("baseline_score")
    is_win = bool(scores) and baseline is not None and max(scores) > baseline
    return {"key": "win", "score": int(is_win)}


def guardrail(run, example) -> dict:
    """금지표현·후보 상한·점수 가드 통과 여부."""
    return {
        "key": "guardrail_passed",
        "score": int(bool((run.outputs or {}).get("guardrail_passed"))),
    }


def schema_valid(run, example) -> dict:
    """제안의 ActionProposal 스키마·해시 적합 여부."""
    return {"key": "schema_valid", "score": int(bool((run.outputs or {}).get("schema_valid")))}


async def main() -> None:
    client = Client()
    sync_dataset(client)
    results = await aevaluate(
        atarget,
        data=DATASET_NAME,
        evaluators=[win, guardrail, schema_valid],
        experiment_prefix="regeneration",
        metadata={"fixture_version": FIXTURE_VERSION},
        client=client,
    )
    print(results)


if __name__ == "__main__":
    asyncio.run(main())
