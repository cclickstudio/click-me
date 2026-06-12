from langsmith import traceable
from openai import AsyncOpenAI

from domain.generator.contracts.schemas import AdCopy, QualityCheckItem, QualityReport
from tools.utils import safe_json_loads

_client = AsyncOpenAI(timeout=60.0)

_SYSTEM = """\
당신은 광고 품질 검증 전문가입니다.
광고 문구를 6개 항목으로 평가하고 반드시 JSON 형식으로만 응답하세요."""

_USER_TEMPLATE = """\
아래 광고 문구를 6개 항목으로 검증하세요.

헤드라인: {headline}
본문: {body}
CTA: {cta}
타겟: {target}

각 항목을 JSON으로 반환하세요:
{{
  "typo_check": {{"passed": bool, "score": 0.0~1.0, "feedback": "설명"}},
  "duplicate_check": {{"passed": bool, "score": 0.0~1.0, "feedback": "설명"}},
  "cta_exists": {{"passed": bool, "score": 0.0~1.0, "feedback": "설명"}},
  "readability": {{"passed": bool, "score": 0.0~1.0, "feedback": "설명"}},
  "target_fit": {{"passed": bool, "score": 0.0~1.0, "feedback": "설명"}},
  "text_length": {{"passed": bool, "score": 0.0~1.0, "feedback": "설명"}}
}}

검증 기준:
- typo_check: 오타·비문 없음
- duplicate_check: 헤드라인/본문/CTA 간 문구 중복 없음
- cta_exists: CTA 문구가 명확히 존재하고 행동 유도
- readability: 누구나 쉽게 이해 가능한 문장
- target_fit: 타겟 고객에게 적합한 표현
- text_length: 헤드라인 20자 이내, 본문 50자 이내, CTA 10자 이내"""


def _parse_item(raw: dict) -> QualityCheckItem:
    return QualityCheckItem(
        passed=bool(raw.get("passed", False)),
        score=float(raw.get("score", 0.5)),
        feedback=str(raw.get("feedback", "")),
    )


@traceable(name="QualityChecker", metadata={"pipeline": "generator"})
async def check_quality(
    ad_copy: AdCopy,
    target: str,
) -> QualityReport:
    response = await _client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.1,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    headline=ad_copy.headline,
                    body=ad_copy.body,
                    cta=ad_copy.cta,
                    target=target,
                ),
            },
        ],
        response_format={"type": "json_object"},
    )

    raw = safe_json_loads(response.choices[0].message.content)

    items = {
        "typo_check": _parse_item(raw.get("typo_check", {})),
        "duplicate_check": _parse_item(raw.get("duplicate_check", {})),
        "cta_exists": _parse_item(raw.get("cta_exists", {})),
        "readability": _parse_item(raw.get("readability", {})),
        "target_fit": _parse_item(raw.get("target_fit", {})),
        "text_length": _parse_item(raw.get("text_length", {})),
    }

    overall_passed = all(v.passed for v in items.values())

    return QualityReport(**items, overall_passed=overall_passed)
