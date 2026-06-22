# 🅰 진단 LLM ReAct — INCONCLUSIVE 케이스를 메타 실신호 tool로 적응 추론한다.
"""진단 agent의 LLM ReAct 경로 (P6 해금분).

결정론 코어(`diagnosis.py`)가 못 가른 INCONCLUSIVE 케이스에 대해, LLM이 메타 실신호 tool
(meta-data-sources §5 매핑)을 적응적으로 호출해 원인 가설을 세운다. 정보 방화벽: tool은
전달된 campaign 한 건만 읽는다. 키 없거나 LLM 실패면 결정론 폴백 — 게이트 #9(키 없이 재현)
불변.

산출은 `DiagnosisResult` 단일 계약. 어떤 경로든 같은 계약·`agent_tool_calls` 기록을 남겨
diagnosis_eval이 tool 효과를 채점할 수 있게 한다(A-5).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from domain.management.contracts.enums import AnomalyType, DiagnosisSource, DiagnosisStatus
from domain.management.contracts.schemas import DiagnosisResult

if TYPE_CHECKING:
    from domain.management.contracts.platform import AdPlatformReader

#: 1회 진단당 tool 호출 상한 (P6) — recursion_limit으로 환산 시 여유분 포함.
MAX_TOOL_CALLS = 6

_VALID_ANOMALIES = {a.value for a in AnomalyType}

_SYSTEM_PROMPT = """너는 광고 게재 진단 보조원이다. 결정론 규칙이 단일 원인을 못 가른
INCONCLUSIVE 케이스만 받는다. 아래 tool로 '이 캠페인'의 실신호만 조회해 원인을 좁혀라
(다른 캠페인·외부 정보 추론 금지 — 정보 방화벽).

신호↔원인 매핑(meta-data-sources §5):
- quality/engagement_rate_ranking 평균 이하 + ctr↓ → quality_degraded
- effective_status=DISAPPROVED 또는 issues_info 존재 → review_rejected
- effective_status=PENDING_REVIEW → review_delay
- learning_stage=LEARNING → learning_phase
- conversion_rate_ranking 평균 이하 + ROAS 목표 미달 → performance_below_target
- 특정 연령·성별 층 성과만 저조 → 세그먼트 근거로 가설 보강

tool은 최대 {max_calls}회만 호출하라. 충분히 모았으면 멈추고, 마지막에 **JSON 한 줄만**
출력하라(설명 금지). 키: anomaly_type(위 값 중 하나 또는 inconclusive),
hypothesis(한국어 한 문장), confidence(0~1 숫자).
예: {{"anomaly_type": "quality_degraded", "hypothesis": "...", "confidence": 0.8}}
"""


def _build_tools(reader: AdPlatformReader, campaign_id: str) -> list[Any]:
    """reader를 campaign에 클로저로 묶은 read-only tool 4종 (정보 방화벽)."""
    from langchain_core.tools import tool  # noqa: PLC0415 — 키 없는 환경 보호(지연 import)

    @tool
    async def read_relevance_diagnostics() -> str:
        """메타 채점표 — quality/engagement/conversion_rate_ranking 백분위."""
        r = await reader.get_relevance_diagnostics(campaign_id)
        return json.dumps(
            {
                "quality_ranking": r.quality_ranking.value,
                "engagement_rate_ranking": r.engagement_rate_ranking.value,
                "conversion_rate_ranking": r.conversion_rate_ranking.value,
            },
            ensure_ascii=False,
        )

    @tool
    async def read_status_detail() -> str:
        """심사·게재 상태 상세 — effective_status / issues_info / learning_stage."""
        s = await reader.get_delivery_status_detail(campaign_id)
        return json.dumps(
            {
                "effective_status": s.effective_status,
                "issues_info": list(s.issues_info),
                "learning_stage": s.learning_stage,
            },
            ensure_ascii=False,
        )

    @tool
    async def read_demographic_breakdown() -> str:
        """연령×성별 성과 분해 — 어떤 층이 성과를 끌어내리는지."""
        rows = await reader.get_demographic_breakdown(campaign_id, _now())
        return json.dumps(
            [
                {"age": r.age, "gender": r.gender, "impressions": r.impressions, "clicks": r.clicks}
                for r in rows
            ],
            ensure_ascii=False,
        )

    @tool
    async def read_metrics() -> str:
        """누적 성과 스냅샷 — impressions/clicks/ctr/cpm/cpc/frequency/roas."""
        m = await reader.get_metrics(campaign_id, _now())
        return json.dumps(
            {
                "impressions": m.impressions,
                "clicks": m.clicks,
                "ctr": m.ctr,
                "cpm_krw": m.cpm_krw,
                "cpc_krw": m.cpc_krw,
                "frequency": m.frequency,
                "roas": m.roas,
            },
            ensure_ascii=False,
        )

    return [
        read_relevance_diagnostics,
        read_status_detail,
        read_demographic_breakdown,
        read_metrics,
    ]


def _now():  # noqa: ANN202 — datetime, 지연 import 회피
    from datetime import UTC, datetime  # noqa: PLC0415

    return datetime.now(UTC)


def _parse_verdict(text: str) -> dict[str, Any] | None:
    """LLM 최종 메시지에서 JSON 평결을 추출 (실패 시 None → 폴백)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


async def run_llm_diagnosis(
    prior: DiagnosisResult,
    reader: AdPlatformReader,
    *,
    model: str,
    temperature: float,
    api_key: str | None,
) -> DiagnosisResult:
    """INCONCLUSIVE 진단을 LLM ReAct로 재판정. 실패·키없음이면 prior 그대로 반환(폴백)."""
    try:
        from langchain_openai import ChatOpenAI  # noqa: PLC0415 — 키 없는 환경 보호
        from langgraph.prebuilt import create_react_agent  # noqa: PLC0415
    except ImportError:
        return prior
    if not api_key:
        return prior

    try:
        llm = ChatOpenAI(model=model, temperature=temperature, api_key=api_key)
        tools = _build_tools(reader, prior.campaign_id)
        agent = create_react_agent(llm, tools)
        prompt = _SYSTEM_PROMPT.format(max_calls=MAX_TOOL_CALLS)
        result = await agent.ainvoke(
            {
                "messages": [
                    ("system", prompt),
                    (
                        "human",
                        f"진단 대상 campaign_id={prior.campaign_id}. 사전 근거: "
                        f"{json.dumps(prior.evidence_metrics, ensure_ascii=False)}",
                    ),
                ]
            },
            {
                "recursion_limit": MAX_TOOL_CALLS * 2 + 1,
                # LangSmith: 진단 에이전트(ReAct)로 식별 — re_evaluate 트레이스의 자식.
                "run_name": "diagnosis_agent",
                "tags": ["management", "diagnosis-agent"],
                "metadata": {"campaign_id": prior.campaign_id},
            },
        )
    except Exception:  # noqa: BLE001 — LLM/네트워크 경계: 어떤 실패든 결정론 폴백(게이트 #9)
        return prior

    messages = result.get("messages", [])
    tool_calls = [m for m in messages if getattr(m, "type", None) == "tool"]
    final_text = getattr(messages[-1], "content", "") if messages else ""
    verdict = _parse_verdict(final_text if isinstance(final_text, str) else "")
    if verdict is None:
        return prior

    anomaly_value = str(verdict.get("anomaly_type", "")).lower()
    anomaly = (
        AnomalyType(anomaly_value) if anomaly_value in _VALID_ANOMALIES else prior.anomaly_type
    )
    confidence = verdict.get("confidence", prior.confidence)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (ValueError, TypeError):
        confidence = prior.confidence
    status = (
        DiagnosisStatus.CONFIRMED
        if anomaly != AnomalyType.INCONCLUSIVE
        else DiagnosisStatus.INCONCLUSIVE
    )
    return prior.model_copy(
        update={
            "anomaly_type": anomaly,
            "source": DiagnosisSource.AGENT,
            "hypothesis": str(verdict.get("hypothesis", prior.hypothesis)),
            "confidence": confidence,
            "status": status,
            "evidence_metrics": {
                **prior.evidence_metrics,
                "agent_tool_calls": [getattr(m, "name", "tool") for m in tool_calls],
            },
        }
    )
