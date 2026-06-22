# 매니지먼트 어시스턴트(에이전틱 RAG) eval — 도구선택 정확도를 LangSmith Experiment로 올린다.
# 실행: cd backend && uv run python -m domain.management.evals.langsmith_assistant_eval
from __future__ import annotations

import asyncio
import os
import sys

os.environ["USE_MOCK"] = "true"  # 어시스턴트 eval은 mock 데이터 위에서 도구선택만 측정 (hermetic)

from dotenv import load_dotenv  # noqa: E402

load_dotenv()
os.environ.setdefault("LANGSMITH_API_KEY", os.environ.get("LANGCHAIN_API_KEY", ""))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from langsmith import Client, aevaluate  # noqa: E402

from domain.management.assistant.contracts import AskRequest  # noqa: E402
from domain.management.evals.assistant_eval import GOLDEN, _make_ask  # noqa: E402

DATASET_NAME = "management-assistant"

# 키 있으면 실제 ReAct, 없으면 결정론 폴백(키워드 라우터) — 1회 빌드해 재사용.
_API_KEY = os.environ.get("OPENAI_API_KEY") or None
_ASK, _MODE, _ = _make_ask(_API_KEY)


def sync_dataset(client: Client) -> str:
    """골든셋(질문→기대 도구)을 LangSmith 데이터셋으로 동기화."""
    rows = [
        {
            "inputs": {"question": q, "campaign_id": cid},
            "outputs": {"expected_tools": sorted(expected)},
            "metadata": {"desc": desc},
        }
        for q, cid, expected, desc in GOLDEN
    ]
    if client.has_dataset(dataset_name=DATASET_NAME):
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        old = list(client.list_examples(dataset_id=ds.id))
        if old:
            client.delete_examples(example_ids=[e.id for e in old])
    else:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="매니지먼트 어시스턴트 도구선택 정확도 — 기대 도구 ⊆ 호출 도구",
        )
    client.create_examples(dataset_id=ds.id, examples=rows)
    print(f"데이터셋 '{DATASET_NAME}' 동기화 — 예시 {len(rows)}개 (mode={_MODE})")
    return DATASET_NAME


async def atarget(inputs: dict) -> dict:
    """질문을 어시스턴트에 넣어 실제로 호출한 도구 목록을 관측한다."""
    res = await _ASK(AskRequest(question=inputs["question"], campaign_id=inputs.get("campaign_id")))
    return {"used_tools": list(res.used_tools), "answer": res.answer}


def tool_accuracy(run, example) -> dict:
    """기대 도구가 모두 호출됐으면 1 (expected ⊆ used). ReAct는 보강 도구를 더 부를 수 있음."""
    used = set((run.outputs or {}).get("used_tools") or [])
    expected = set((example.outputs or {}).get("expected_tools") or [])
    return {"key": "tool_accuracy", "score": int(expected <= used)}


async def main() -> None:
    client = Client()
    sync_dataset(client)
    results = await aevaluate(
        atarget,
        data=DATASET_NAME,
        evaluators=[tool_accuracy],
        experiment_prefix="assistant",
        metadata={"mode": _MODE},
        client=client,
    )
    print(results)


if __name__ == "__main__":
    asyncio.run(main())
