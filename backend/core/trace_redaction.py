# LangSmith 트레이스 전송 전 기밀(예산·크리에이티브·자격증명)을 키 이름 기준으로 가리는 redactor.
from __future__ import annotations

from typing import Any

# 키 이름에 아래 조각이 포함되면(대소문자 무시) 값을 마스킹한다.
# - krw : 모든 금액 필드(daily_budget_krw·spend_krw·budget_before/after_krw·max_total_spend_krw 등)
# - budget/spend : 금액 일반(_krw 접미사 없는 변형 대비)
# - headline/primary_text : 크리에이티브 본문(광고 제목·문구)
# - secret/password/api_key/access_token : 자격증명 방어
# 식별자(campaign_id·creative_ad_id 등)는 디버깅에 필요하므로 남긴다 — 본문/금액만 가린다.
_SENSITIVE_KEY_PARTS = (
    "krw",
    "budget",
    "spend",
    "headline",
    "primary_text",
    "secret",
    "password",
    "api_key",
    "access_token",
)
_REDACTED = "[REDACTED]"


def _is_sensitive(key: str) -> bool:
    k = key.lower()
    return any(part in k for part in _SENSITIVE_KEY_PARTS)


def redact(data: Any) -> Any:
    """dict/list 재귀 순회하며 기밀 키 값을 [REDACTED]로 치환. 그 외(지표·추론)는 보존."""
    if isinstance(data, dict):
        return {k: (_REDACTED if _is_sensitive(str(k)) else redact(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact(v) for v in data]
    return data
