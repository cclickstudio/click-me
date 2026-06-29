# 어시스턴트 답변 충실도(faithfulness) 베이스라인 — 에이전트(OpenAI) 실행 → Gemini judge 채점.
"""KB 질문을 실제 에이전트로 돌려 답을 만들고, 근거(검색 청크+실측) 대비 지지 여부를 채점한다.

측정 대상(에이전트)=OpenAI gpt-4o-mini(운영 그대로), 채점자(judge)=Gemini 2.0 Flash(저비용).
실행: cd backend && uv run python -m domain.management.evals.faithfulness_eval
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import statistics
from pathlib import Path

import google.generativeai as genai

from core.config import settings
from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest
from domain.management.assistant.retriever import KbRetriever
from domain.management.evals.retrieval_eval import CASES

#: 진행/결과를 한 건씩 적재 — 중간 중단돼도 부분 결과 보존(이 파일을 읽어 진행 확인).
RESULTS = Path(__file__).parent / "_faithfulness_results.jsonl"


def _append(obj: dict) -> None:
    with RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


_JUDGE_PROMPT = """너는 RAG 답변의 환각 채점자다. 질문·근거·답변을 보고 JSON으로만 답하라.
핵심 기준: 답변에 '환각'(근거와 모순되거나 거짓인 주장)이 있는가.
- 감점 대상: 근거와 모순되는 내용, 사실 오류, '근거에 없는데 지어낸 구체 수치'(지출·CTR·ROAS 등).
- 감점 아님: KB에 명시되진 않았어도 '사실이고 합리적인 일반 광고 지식'(거짓이 아니면 OK).
- 숫자는 근거(실측)에 있을 때만 인정. 근거 밖 수치를 단언하면 감점.
faithful=true는 '환각·사실오류·지어낸 수치가 없음'을 뜻한다(모든 문장이 KB에 있을 필요는 없다).
출력 JSON 스키마: {{"faithful": true|false, "score": 1, "unsupported": [], "reason": ""}}
(score 1~5: 5=환각 전혀 없음, 1=명백한 환각/거짓 다수)

[질문]
{q}

[근거]
{evidence}

[답변]
{answer}
"""


def _parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {"faithful": False, "score": 0, "unsupported": ["parse_fail"], "reason": text[:80]}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {"faithful": False, "score": 0, "unsupported": ["json_fail"], "reason": text[:80]}


async def run() -> dict:
    key = getattr(settings, "gemini_api_key", None) or os.environ["GEMINI_API_KEY"]
    genai.configure(api_key=key)
    judge = genai.GenerativeModel("gemini-2.5-flash")
    ask = build_management_agent(settings)
    r = KbRetriever(api_key=settings.openai_api_key)

    j_runs = 3  # judge 반복 — 확률적 채점 노이즈를 평균화(에이전트는 temp 0이라 1회로 충분)
    scores: list[float] = []
    faithful = 0
    case_stds: list[float] = []
    n = len(CASES)
    RESULTS.write_text("", encoding="utf-8")  # 초기화
    _append({"meta": {"n": n, "judge_runs": j_runs}})
    print(f"=== Faithfulness 측정 (n={n}, judge×{j_runs} 평균, 에이전트=OpenAI, judge=Gemini) ===")
    for i, (q, _src, _sec) in enumerate(CASES, 1):
        try:
            res = await ask(AskRequest(question=q))
            chunks = await r.search(q, k=4)
            evidence = "\n".join(
                f"- [{c['source']}] {c['title']}: {c['chunk'][:300]}" for c in chunks
            )
            if res.evidence:
                evidence += f"\n- 실측: {json.dumps(res.evidence, ensure_ascii=False)[:400]}"
            prompt = _JUDGE_PROMPT.format(q=q, evidence=evidence, answer=res.answer)
            cs: list[int] = []
            cf: list[bool] = []
            for _ in range(j_runs):
                verdict = _parse(judge.generate_content(prompt).text)
                cs.append(int(verdict.get("score") or 0))
                cf.append(bool(verdict.get("faithful")))
            mean_c = sum(cs) / j_runs
            is_faithful = sum(cf) > j_runs / 2  # 과반 투표
            std_c = statistics.pstdev(cs)
            scores.append(mean_c)
            faithful += is_faithful
            case_stds.append(std_c)
            mark = "✓" if is_faithful else "✗"
            _append(
                {
                    "i": i,
                    "q": q,
                    "score": round(mean_c, 2),
                    "std": round(std_c, 2),
                    "faithful": is_faithful,
                    "votes": f"{sum(cf)}/{j_runs}",
                }
            )
            print(f"  {mark} [{mean_c:.1f}±{std_c:.1f}] {q[:22]:24s} faithful {sum(cf)}/{j_runs}")
        except Exception as exc:  # noqa: BLE001
            _append({"i": i, "q": q, "error": str(exc)})
            print(f"  ! {q[:22]:24s} 오류: {exc}")
            scores.append(0)
            case_stds.append(0)
    mean = round(sum(scores) / n, 2) if n else 0
    out = {
        "n": n,
        "judge_runs": j_runs,
        "mean_score": mean,
        "faithful_rate": round(faithful / n, 3),
        "avg_judge_std": round(sum(case_stds) / n, 2),  # 잔여 채점 노이즈(낮을수록 정밀)
    }
    _append({"summary": out})
    print(
        f"\n  평균 score={out['mean_score']}/5  faithful_rate={out['faithful_rate']}  "
        f"잔여 judge표준편차(평균)={out['avg_judge_std']}"
    )
    return out


if __name__ == "__main__":
    asyncio.run(run())
