# 캠페인 이름 자동 제안 — 소재(ads)·시뮬 집계를 재료로 규칙 조합 + (키 있으면) gpt-4o-mini 보강
"""제너레이터→시뮬→매니지먼트 흐름의 도착점에서 캠페인 이름 후보를 만든다.

원칙: LLM이 없거나 실패해도 규칙 기반 후보가 항상 나온다(결정론 폴백 — 폼이 비지 않게).
입력은 core.models.Ad의 컬럼(제목·카피·카테고리·타깃 필터)과 시뮬 집계뿐 — 타 도메인
내부 모델 import 없음.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("clickme")

_MAX_NAME_LEN = 40  # Meta 캠페인 이름은 길면 목록에서 잘림 — 표시 안전 길이
_OBJECTIVE_LABEL = {"traffic": "트래픽", "leads": "리드"}


def _target_label(target_filter: dict | None) -> str | None:
    """target_filter(JSONB)에서 '2534여성' 같은 짧은 타깃 라벨을 만든다 — 없으면 None."""
    if not isinstance(target_filter, dict):
        return None
    age_min = target_filter.get("age_min")
    age_max = target_filter.get("age_max")
    gender = str(target_filter.get("gender") or "").lower()
    gender_ko = {"male": "남성", "female": "여성"}.get(gender)
    if age_min and age_max:
        age = f"{int(age_min) % 100}{int(age_max) % 100}"
        return f"{age}{gender_ko or ''}" or None
    return gender_ko


def _clip(name: str) -> str:
    return name[:_MAX_NAME_LEN].rstrip("_· ")


def rule_based_names(
    *,
    title: str | None,
    copy_text: str | None,
    product_category: str | None,
    industry_category: str | None,
    target_filter: dict | None,
    objective: str,
    click_intent_rate: float | None,
    now: datetime | None = None,
) -> list[str]:
    """결정론 후보 3개 — [핵심 소재]_[타깃]_[목표]_[월] 조합 변형."""
    month = (now or datetime.now(UTC)).month
    obj = _OBJECTIVE_LABEL.get(objective, objective)
    base = (product_category or industry_category or title or "신규 캠페인").strip()
    target = _target_label(target_filter)
    # 카피 첫 구절 — 감성 소구 한 조각(문장부호 전까지 12자 이내)
    hook = None
    if copy_text:
        first = copy_text.strip().split("\n")[0]
        for sep in (".", "!", "?", "—", "·"):
            first = first.split(sep)[0]
        hook = first.strip()[:12] or None

    parts_a = [base, target, obj, f"{month}월"]
    parts_b = [hook or base, obj, f"{month}월"]
    parts_c = [base, "시뮬검증" if (click_intent_rate or 0) >= 0.2 else None, obj]
    out = []
    for parts in (parts_a, parts_b, parts_c):
        name = _clip("_".join(p for p in parts if p))
        if name and name not in out:
            out.append(name)
    return out[:3]


async def suggest_campaign_names(
    *,
    ad: dict[str, Any],
    objective: str = "traffic",
    click_intent_rate: float | None = None,
    openai_api_key: str | None = None,
) -> list[str]:
    """이름 후보 3개 — 키가 있으면 gpt-4o-mini로 다듬고, 실패·부재 시 규칙 후보 그대로."""
    fallback = rule_based_names(
        title=ad.get("title"),
        copy_text=ad.get("copy_text"),
        product_category=ad.get("product_category"),
        industry_category=ad.get("industry_category"),
        target_filter=ad.get("target_filter"),
        objective=objective,
        click_intent_rate=click_intent_rate,
    )
    if not openai_api_key:
        return fallback
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415 — 키 있을 때만 로드

        client = AsyncOpenAI(api_key=openai_api_key, timeout=6.0)
        prompt = (
            "다음 광고로 만들 Meta 캠페인의 이름 후보 3개를 만들어줘.\n"
            f"- 소재 제목: {ad.get('title') or '-'}\n"
            f"- 카피: {(ad.get('copy_text') or '-')[:200]}\n"
            f"- 제품/업종: {ad.get('product_category') or ad.get('industry_category') or '-'}\n"
            f"- 캠페인 목표: {_OBJECTIVE_LABEL.get(objective, objective)}\n"
            "규칙: 한국어, 각 25자 이내, 목록에서 구분 잘 되게 [소구]_[타깃/제품]_[목표] 형태,"
            ' 이모지 금지. JSON 배열로만 답해: ["...", "...", "..."]'
        )
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=120,
        )
        raw = (resp.choices[0].message.content or "").strip()
        start, end = raw.find("["), raw.rfind("]")
        names = json.loads(raw[start : end + 1]) if start >= 0 and end > start else []
        names = [_clip(str(n)) for n in names if str(n).strip()][:3]
        return names or fallback
    except Exception:  # noqa: BLE001 — 이름 제안은 부가 기능, 실패해도 폼을 막지 않는다
        logger.info("캠페인 이름 LLM 제안 실패 — 규칙 후보로 폴백")
        return fallback
