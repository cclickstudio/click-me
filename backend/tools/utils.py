from __future__ import annotations

import json
import re


def safe_json_loads(text: str | None, fallback: str = "{}") -> dict | list:
    """Parse LLM JSON output, stripping markdown code fences if present."""
    raw = (text or "").strip()
    if not raw:
        return json.loads(fallback)
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw.strip())
        raw = raw.strip()
    return json.loads(raw)


def str_or_none(val) -> str | None:
    if val is None:
        return None
    return str(val) if not isinstance(val, str) else val


def str_list(val) -> list[str]:
    if not val:
        return []
    if isinstance(val, dict):
        return [str(k) for k in val]
    if isinstance(val, list):
        return [str(v) for v in val]
    return [str(val)]
