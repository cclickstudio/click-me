# 🅰 어시스턴트(에이전틱 RAG) eval — 도구선택 정확도 · trajectory · faithfulness
"""에이전트가 '질문에 맞는 도구를 골랐는가'와 '수치를 근거(live)에서만 인용했는가'를 잰다.

- 키 없음(게이트 #9): 결정론 폴백(키워드 라우터)으로 재현 — tool-accuracy/trajectory만.
- 키 있음: mock reader(결정론 데이터) 위에서 실제 ReAct 도구선택을 측정 + LLM-judge faithfulness.

정답은 '기대 도구를 호출했는가'(현실 일치가 아님 — mock은 평가 하니스). diagnosis_eval과 같은 철학.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import HumanMessage

from domain.management.assistant.agent import build_management_agent
from domain.management.assistant.contracts import AskRequest, AskResult

_AskFn = Callable[[AskRequest], Awaitable[AskResult]]

# 골든셋 — (질문, campaign_id, 반드시 호출해야 하는 도구 집합, 설명).
# expected ⊆ used_tools 이면 통과. ReAct는 보강 도구(search_kb 등)를 더 부를 수 있다.
GOLDEN: list[tuple[str, str | None, set[str], str]] = [
    ("이번 달 예산 소진 얼마야?", None, {"live_budget"}, "예산 페이싱"),
    ("런레이트로 보면 월말 예상 지출은?", None, {"live_budget"}, "런레이트"),
    ("지금 운영 중인 캠페인 목록 보여줘", None, {"live_campaigns"}, "전체 현황"),
    ("이 캠페인 왜 게재가 안 돼?", "camp_1", {"live_campaign_detail"}, "단일 캠페인 진단"),
    ("camp_1 지금 성과 어때?", "camp_1", {"live_campaign_detail"}, "단일 캠페인 성과"),
    ("예측대로 성과가 나왔는지 비교해줘", None, {"live_before_after"}, "전후비교"),
    ("CPM이 12000원이면 비싼 거야?", None, {"search_kb"}, "벤치마크 CPM 기준"),
    ("트래픽 광고 CTR 기준이 어떻게 돼?", None, {"search_kb"}, "벤치마크 CTR 기준"),
    ("틱톡은 CPM이 어때?", None, {"search_kb"}, "advisory 멀티플랫폼"),
]


@dataclass
class AssistantEvalResult:
    mode: str  # "react"(키 있음) | "fallback"(키 없음)
    tool_accuracy: float  # expected ⊆ used 비율
    avg_tools_used: float  # 평균 도구 호출 수(trajectory)
    faithfulness: float | None  # 수치 근거성(LLM-judge), 키 없으면 None
    n_cases: int
    per_case: list[tuple[str, bool, list[str]]] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return self.tool_accuracy >= 0.8


def _make_ask(api_key: str | None) -> tuple[_AskFn, str, object | None]:
    """평가용 ask 함수 — 키 있으면 mock 데이터 위 ReAct, 없으면 결정론 폴백."""
    mock_settings = SimpleNamespace(use_mock=True, openai_api_key=None)
    if not api_key:
        return build_management_agent(mock_settings), "fallback", None

    from langchain_openai import ChatOpenAI  # noqa: PLC0415
    from langgraph.checkpoint.memory import MemorySaver  # noqa: PLC0415

    from domain.management.assistant.graph import build_graph, to_result  # noqa: PLC0415

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=api_key)
    # retriever=None — KB 미연결로도 도구선택은 측정 가능(search_kb는 빈 결과로 동작)
    graph = build_graph(mock_settings, None, llm, checkpointer=MemorySaver())

    async def ask(req: AskRequest) -> AskResult:
        final = await graph.ainvoke(
            {"messages": [HumanMessage(content=req.question)], "campaign_id": req.campaign_id},
            config={"configurable": {"thread_id": uuid4().hex}},
        )
        if final.get("__interrupt__"):
            return AskResult(answer="(승인 대기)", used_tools=list(final.get("used_tools", [])))
        return to_result(final)

    return ask, "react", llm


_NUM = re.compile(r"[\d][\d,]*")


async def _judge_faithful(llm, question: str, answer: str, evidence: dict) -> bool:
    """답변의 수치가 evidence(live)에서만 나왔는지 LLM으로 채점."""
    sys = (
        "너는 사실성 평가자다. 답변에 등장하는 모든 수치가 주어진 근거(evidence)에 실제로 있는지 "
        '판단해 JSON으로만: {"faithful": true|false}. 근거에 없는 수치를 지어냈으면 false.'
    )
    user = (
        f"질문: {question}\n답변: {answer}\n"
        f"근거(evidence): {json.dumps(evidence, ensure_ascii=False)}"
    )
    resp = await llm.ainvoke([("system", sys), ("human", user)])
    text = resp.content if isinstance(resp.content, str) else str(resp.content)
    t = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return bool(json.loads(t).get("faithful", False))
    except (ValueError, TypeError):
        # 폴백 — 답변 숫자가 evidence 직렬화에 포함되는지 결정론 확인
        ev = json.dumps(evidence, ensure_ascii=False)
        return all(n.replace(",", "") in ev.replace(",", "") for n in _NUM.findall(answer))


async def run(api_key: str | None = None) -> AssistantEvalResult:
    """골든셋으로 도구선택 정확도·trajectory·faithfulness를 측정한다."""
    if api_key is None:
        from core.config import settings  # noqa: PLC0415

        api_key = getattr(settings, "openai_api_key", None)

    ask, mode, judge = _make_ask(api_key)
    matches = 0
    tool_counts = 0
    faithful_hits = 0
    faithful_total = 0
    per_case: list[tuple[str, bool, list[str]]] = []

    for question, cid, expected, _desc in GOLDEN:
        res = await ask(AskRequest(question=question, campaign_id=cid))
        used = set(res.used_tools)
        ok = expected <= used
        matches += int(ok)
        tool_counts += len(res.used_tools)
        per_case.append((question, ok, res.used_tools))
        if judge is not None and res.evidence and res.answer:
            faithful_total += 1
            faithful_hits += int(await _judge_faithful(judge, question, res.answer, res.evidence))

    n = len(GOLDEN)
    return AssistantEvalResult(
        mode=mode,
        tool_accuracy=round(matches / n, 3) if n else 0.0,
        avg_tools_used=round(tool_counts / n, 2) if n else 0.0,
        faithfulness=round(faithful_hits / faithful_total, 3) if faithful_total else None,
        n_cases=n,
        per_case=per_case,
    )


if __name__ == "__main__":
    r = asyncio.run(run())
    gate = "통과" if r.passes else "실패"
    print(f"[어시스턴트 eval] mode={r.mode}  도구정확도={r.tool_accuracy}  게이트(≥0.8)={gate}")
    print(f"  케이스={r.n_cases}  평균 도구호출={r.avg_tools_used}  faithfulness={r.faithfulness}")
    for q, ok, used in r.per_case:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {q}  → {used}")
