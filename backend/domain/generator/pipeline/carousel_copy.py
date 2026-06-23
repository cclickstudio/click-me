# 캐러셀(카드뉴스) 슬라이드 카피 — 고정 5역할을 1콜로 생성
from __future__ import annotations

from langsmith import traceable
from pydantic import BaseModel, Field

from domain.generator.contracts.pipeline_schemas import ProductAnalysis
from domain.generator.llm.factory import build_text_llm

# 고정 역할(순서) — 문제제기 → 특징 → 차별점 → 후기(예시) → CTA
CAROUSEL_ROLES = ("문제 제기", "제품 특징", "차별점", "후기(예시)", "CTA")


class CarouselSlide(BaseModel):
    """슬라이드 1장 카피."""

    role: str
    headline: str
    body: str
    cta: str | None = None  # 마지막 CTA 슬라이드만 버튼 문구


class CarouselScript(BaseModel):
    """캐러셀 5장 스크립트."""

    slides: list[CarouselSlide] = Field(default_factory=list)


_SYSTEM = """당신은 카드뉴스형 캐러셀 광고 카피라이터입니다.
제품 분석을 바탕으로 정확히 5장의 슬라이드 카피를 순서대로 작성하세요. 역할은 고정입니다.
1) 문제 제기 — 타깃의 페인포인트를 짧고 공감되게
2) 제품 특징 — 핵심 특징 1~2가지
3) 차별점 — 경쟁/대안 대비 강점
4) 후기(예시) — 그럴듯한 사용 후기 한 줄 (반드시 가상의 '예시' — 과장·허위 금지)
5) CTA — 행동 유도, cta에 버튼 문구

각 슬라이드: role(위 역할 그대로)·headline(짧게)·body(1~2문장). 5번만 cta 채움.
한국어, 오탈자·비문 금지."""


def _build_prompt(p: ProductAnalysis) -> str:
    return (
        f"제품: {p.product_name}\n"
        f"핵심 가치: {', '.join(p.core_values) or '-'}\n"
        f"페인포인트: {', '.join(p.pain_points) or '-'}\n"
        f"혜택: {', '.join(p.benefits) or '-'}\n"
        f"타깃: {p.target_audience or '일반 소비자'}\n"
        f"목적: {p.objective or '-'}"
    )


_llm = build_text_llm(temperature=0.6, max_tokens=700).with_structured_output(CarouselScript)


@traceable(
    name="generator:carousel_copy", metadata={"pipeline": "generator", "prompt_version": "v1.0"}
)
async def generate_carousel_copy(product_analysis: ProductAnalysis) -> CarouselScript:
    """제품 분석으로 캐러셀 5장 카피를 생성한다."""
    response = await _llm.ainvoke([("system", _SYSTEM), ("user", _build_prompt(product_analysis))])
    return response  # type: ignore[return-value]
