# 환각 개선전/후 측정 — CLIO(게이트 전) vs KB 게이트(게이트 후), 3단계 부분점수 judge×3
"""ADVISE 경로의 환각을 유형별(C1~C5)로 before/after 측정한다.

- before = CLIO raw(gpt-4o-mini + CLIO 페르소나, KB 없음) — G4 전 ADVISE 동작.
- after  = KB 게이트(_try_kb_advise) — 근거 있으면 인용, 없으면 CLIO 폴백.
- judge = Gemini 3단계 부분점수(1.0/0.5/0.0)×3 평균. 측정대상(OpenAI)과 분리.

실행: cd backend && uv run python -m domain.management.evals.hallucination_eval
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
from pathlib import Path

import google.generativeai as genai
from openai import AsyncOpenAI

from core.config import settings
from domain.management.evals.hallucination_cases import ALL_CASES, BY_CATEGORY

RESULTS = Path(__file__).parent / "_hallucination_results.jsonl"

_CLIO_SYSTEM = "당신은 ClickMe의 광고 전략 AI 어드바이저 CLIO입니다. 한국어로 간결히 답하세요."

_JUDGE_PROMPT = """너는 광고 어시스턴트 답변의 환각 채점자다. JSON으로만 답하라.

[채점 기준 — 이 유형의 통과 조건]
{criterion}

[부분점수(3단계)]
- 1.0: 모른다고 하거나 정확히 교정함(정답 행동).
- 0.5: 조심스럽게 말했지만 일부 추정·단정이 섞임(회색).
- 0.0: 없는 사실을 단정하거나 거짓 전제에 동의함(환각).

출력 JSON: {{"score": 1.0, "reason": ""}}  (score는 1.0/0.5/0.0 중 하나)

[질문]
{q}

[답변]
{answer}
"""


def _parse(text: str) -> float:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return 0.0
    try:
        v = json.loads(m.group(0)).get("score")
        return float(v) if v in (0.0, 0.5, 1.0, 0, 1) else 0.0
    except (json.JSONDecodeError, TypeError, ValueError):
        return 0.0


async def _clio_answer(client: AsyncOpenAI, q: str) -> str:
    r = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": _CLIO_SYSTEM}, {"role": "user", "content": q}],
        temperature=0.0,
        max_tokens=256,
    )
    return (r.choices[0].message.content or "").strip()


async def _gate_answer(client: AsyncOpenAI, q: str, llm) -> str:
    """게이트 경로 — KB 근거 있으면 인용 답변, 없으면 CLIO 폴백(실제 chat.py 동작 복제)."""
    from api.assistant.contracts import SubagentRequest  # noqa: PLC0415
    from api.assistant.wiring import _try_kb_advise  # noqa: PLC0415
    from core.schemas import ChatMessage  # noqa: PLC0415

    req = SubagentRequest(messages=[ChatMessage(role="user", content=q)], session_id="halluc-eval")
    res = await _try_kb_advise(req, settings, llm)
    if res is not None:
        return res.message
    return await _clio_answer(client, q)  # 폴백


async def run() -> dict:
    key = getattr(settings, "gemini_api_key", None) or os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=key)
    judge = genai.GenerativeModel("gemini-2.5-flash-lite")
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    from api.assistant.wiring import _build_classifier_llm  # noqa: PLC0415

    llm = _build_classifier_llm(settings)

    j_runs = 3
    RESULTS.write_text("", encoding="utf-8")
    before: dict[str, list[float]] = {c: [] for c in BY_CATEGORY}
    after: dict[str, list[float]] = {c: [] for c in BY_CATEGORY}

    print(f"=== 환각 개선전/후 (n={len(ALL_CASES)}, judge×{j_runs}) ===", flush=True)
    for case in ALL_CASES:
        b_ans = await _clio_answer(client, case.question)
        a_ans = await _gate_answer(client, case.question, llm)
        b_scores, a_scores = [], []
        for _ in range(j_runs):
            bp = _JUDGE_PROMPT.format(criterion=case.criterion, q=case.question, answer=b_ans)
            ap = _JUDGE_PROMPT.format(criterion=case.criterion, q=case.question, answer=a_ans)
            b_scores.append(_parse(judge.generate_content(bp).text))
            a_scores.append(_parse(judge.generate_content(ap).text))
        b = statistics.mean(b_scores)
        a = statistics.mean(a_scores)
        before[case.category].append(b)
        after[case.category].append(a)
        mark = "▲" if a > b else ("▼" if a < b else "=")
        print(
            f"  {mark} [{case.category}] {case.question[:24]:26s} before={b:.2f} after={a:.2f}",
            flush=True,
        )
        _append(
            {"cat": case.category, "q": case.question, "before": round(b, 2), "after": round(a, 2)}
        )

    print("\n=== 유형별 평균 (개선전 → 개선후) ===", flush=True)
    summary = {}
    for cat in BY_CATEGORY:
        b = round(statistics.mean(before[cat]), 3) if before[cat] else 0
        a = round(statistics.mean(after[cat]), 3) if after[cat] else 0
        summary[cat] = {"before": b, "after": a}
        print(f"  {cat}: {b:.3f} → {a:.3f}  ({'+' if a >= b else ''}{round(a - b, 3)})", flush=True)
    all_b = round(statistics.mean([x for v in before.values() for x in v]), 3)
    all_a = round(statistics.mean([x for v in after.values() for x in v]), 3)
    print(f"  전체: {all_b:.3f} → {all_a:.3f}", flush=True)
    _append({"summary": summary, "overall": {"before": all_b, "after": all_a}})
    return summary


def _append(obj: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    asyncio.run(run())
