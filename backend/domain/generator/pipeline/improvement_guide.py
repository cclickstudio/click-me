# 개선점 3단계 분류기 — 시뮬 결과·사용자 요청을 종합해 이미지 생성 지시문 list[str] 출력
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from domain.generator.llm.factory import build_text_llm, with_llm_retry

_SYSTEM = """당신은 광고 개선 방향 분류기입니다.
주어진 시뮬레이션 결과와 사용자 수정 요청을 종합해,
이미지·카피 생성에 직접 반영할 구체적인 지시문 목록을 출력하세요.

각 지시문 형식: "{광고 요소}를 {방향}하라 ({근거} → {단계})"

단계 정의:
- Enhance: 해당 요소가 광고에서 부족하거나 약함 → 더 강조·크게·눈에 띄게
- Keep: 현재 수준이 효과적으로 작동 중 → 현재 수준 그대로 유지
- Reduce: 해당 요소가 지나쳐 거부감·역효과 발생 → 줄이거나 부드럽게

원칙:
- 사용자 fix_requests와 시뮬레이션 신호가 충돌하면 절충안을 만들어라
- 이미지·카피로 직접 반영 가능한 것만 포함
  (가격 인하·배송 개선 등 비즈니스 조치 필요 항목은 제외)
- 2~5개 지시문, 중요한 순서로
- 한국어로 작성"""

_USER_TEMPLATE = """시뮬레이션 요약: {simulation_summary}
AI 분석: {plain_summary}
개선 방향(ranked_actions): {improvement_direction}
사용자 수정 요청: {fix_requests}"""


class _ClassifierOutput(BaseModel):
    directives: list[str] = Field(default_factory=list)


_llm = with_llm_retry(
    build_text_llm(temperature=0.3, max_tokens=500).with_structured_output(_ClassifierOutput)
)


@traceable(name="generator:classify_improvements", metadata={"pipeline": "generator"})
async def classify_improvements(
    simulation_summary: str | None,
    plain_summary: str | None,
    improvement_direction: str | None,
    fix_requests: str | None,
) -> list[str]:
    """시뮬 결과 + 사용자 요청을 종합해 이미지 생성 지시문 list[str]을 반환한다."""
    if not any([simulation_summary, plain_summary, improvement_direction, fix_requests]):
        return []
    prompt = _USER_TEMPLATE.format(
        simulation_summary=simulation_summary or "(없음)",
        plain_summary=plain_summary or "(없음)",
        improvement_direction=improvement_direction or "(없음)",
        fix_requests=fix_requests or "(없음)",
    )
    result = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
    return result.directives
