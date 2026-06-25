# 개선점 분류 — 이미지 재생성으로 적용 가능한 것 / 별도 조치가 필요한 것으로 분리
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from domain.generator.llm.factory import build_text_llm

_SYSTEM = """당신은 광고 개선점 분류기입니다.
입력(사용자 수정 요청, 시뮬레이션 개선 방향)의 각 개선점을 두 갈래로 분류하세요.

image_actions — 광고 이미지·카피 재생성으로 바로 반영 가능한 것 (우선순위 높은 순서로):
- 시각/카피 변경(색감·강조 문구·구도·톤·레이아웃 등)은 여기.
- 가격·배송·후기·수치도 "사용자가 구체적 정보를 제공했다면" 여기에 넣고 우선 반영
  (예: "9,900원 특가로 표시", "무료배송 강조", "별점 4.8 노출").
- 사용자 수정 요청이 시뮬레이션 개선 방향보다 항상 우선.

guidance — 광고 이미지로는 해결 불가, 실제 데이터·비즈니스 조치·사용자 입력이 필요한 것:
- 구체 정보 없이 "가격을 낮춰라", "배송을 개선하라", "후기를 늘려라" 같은 항목.
- 각 항목에 '무엇이 필요한지'와 '어떻게 적용하면 되는지'를 1~2문장으로 안내.

한국어로, 각 항목은 간결한 한 줄로."""

_USER_TEMPLATE = """사용자 수정 요청: {fix_requests}
시뮬레이션 개선 방향: {improvement_direction}"""


class ImprovementSplit(BaseModel):
    """개선점 분류 결과."""

    image_actions: list[str] = Field(default_factory=list)  # 이미지/카피로 바로 적용(우선순위순)
    guidance: list[str] = Field(default_factory=list)  # 이미지로 불가 — 데이터/조치 필요 + 적용법


_llm = build_text_llm(temperature=0.2, max_tokens=600).with_structured_output(ImprovementSplit)


@traceable(name="generator:split_improvements", metadata={"pipeline": "generator"})
async def split_improvements(
    fix_requests: str | None, improvement_direction: str | None
) -> ImprovementSplit:
    """개선 입력을 이미지 적용 가능(image_actions) / 별도 조치(guidance)로 분류한다."""
    if not (fix_requests or improvement_direction):
        return ImprovementSplit()
    prompt = _USER_TEMPLATE.format(
        fix_requests=fix_requests or "(없음)",
        improvement_direction=improvement_direction or "(없음)",
    )
    return await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
