"""노드 5 — QA Harness: 7항목 품질 검증 (계획서 8장, Generator QA 정책 13장).

검증 항목: CTA 존재 / 문구 길이 / 후보 간 문구 중복 (결정적)
         + 오타 / 가독성 / 타겟 적합성 / 브랜드 일관성 (LLM)
QA 실패는 파이프라인을 중단하지 않으며 메타데이터로만 저장된다.
"""

from __future__ import annotations

import asyncio
import difflib
import json

from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

from core.config import settings
from domain.generator.contracts.schemas import LLMQAResult, QACheck, QAResult
from domain.generator.graph.nodes import emit_progress
from domain.generator.graph.state import GenerationState

_llm = ChatOpenAI(
    model=settings.generator_text_model,
    api_key=settings.openai_api_key,
    temperature=0.0,
).with_structured_output(LLMQAResult)

_SYSTEM = """당신은 광고 품질 검수 전문가입니다. 광고 카피를 다음 4가지 기준으로 검증하세요.
- typo: 맞춤법·띄어쓰기 오류가 없는가
- readability: 문구가 한눈에 읽히고 이해되는가
- target_fit: 타겟 소비자에게 적합한 표현·어조인가
- brand_consistency: 브랜드 톤앤매너와 일관되는가 (브랜드 정보 없으면 카피 간 일관성 기준)
각 항목에 passed(true/false)와 한국어 근거(detail)를 작성하세요."""

# 결정적 체크 기준 (카피 시스템 프롬프트의 길이 제한 + 여유분)
_MAX_LEN = {"headline": 20, "subcopy": 35, "benefit_text": 40, "cta": 14}
_DUP_THRESHOLD = 0.85


def check_cta_presence(copy: dict) -> QACheck:
    cta = (copy.get("cta") or "").strip()
    return QACheck(
        name="cta_presence",
        passed=bool(cta),
        detail=f'CTA: "{cta}"' if cta else "CTA 문구가 비어 있음",
    )


def check_copy_length(copy: dict) -> QACheck:
    violations = [
        f"{field} {len((copy.get(field) or '').strip())}자 > {limit}자"
        for field, limit in _MAX_LEN.items()
        if len((copy.get(field) or "").strip()) > limit
    ]
    return QACheck(
        name="copy_length",
        passed=not violations,
        detail="; ".join(violations) if violations else "모든 문구가 길이 기준 충족",
    )


def check_duplication(copy: dict, other_copies: list[dict]) -> QACheck:
    """다른 후보들과 헤드라인 유사도 비교 — 후보 간 차별성 검증."""
    headline = copy.get("headline") or ""
    for other in other_copies:
        ratio = difflib.SequenceMatcher(None, headline, other.get("headline") or "").ratio()
        if ratio > _DUP_THRESHOLD:
            return QACheck(
                name="duplication",
                passed=False,
                detail=f'헤드라인 유사도 {ratio:.2f}: "{headline}" ≈ "{other.get("headline")}"',
            )
    return QACheck(name="duplication", passed=True, detail="후보 간 문구 중복 없음")


async def run_qa(state: GenerationState, config: RunnableConfig) -> dict:
    emit_progress(config, "qa", 85, "품질 검증 중...")
    candidates = state["candidates"]
    req = state["request"]

    async def qa_one(candidate: dict) -> dict:
        copy = candidate["copy"]
        other_copies = [c["copy"] for c in candidates if c["idx"] != candidate["idx"]]
        checks = [
            check_cta_presence(copy),
            check_copy_length(copy),
            check_duplication(copy, other_copies),
        ]

        prompt = (
            f"광고 카피: {json.dumps(copy, ensure_ascii=False)}\n"
            f"타겟: {req['target_audience']}\n"
            f"톤앤매너: {req.get('tone_and_manner') or '(미지정)'}\n"
            f"전략: {candidate['strategy']['name']}"
        )
        llm_result: LLMQAResult = await _llm.ainvoke([("system", _SYSTEM), ("user", prompt)])
        checks += [
            QACheck(name="typo", **llm_result.typo.model_dump()),
            QACheck(name="readability", **llm_result.readability.model_dump()),
            QACheck(name="target_fit", **llm_result.target_fit.model_dump()),
            QACheck(name="brand_consistency", **llm_result.brand_consistency.model_dump()),
        ]
        return QAResult(checks=checks, passed=all(c.passed for c in checks)).model_dump()

    results = await asyncio.gather(*[qa_one(c) for c in candidates])
    return {"qa_results": list(results)}
