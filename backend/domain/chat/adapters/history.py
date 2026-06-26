# 대화 히스토리를 서브에이전트 질문 앞에 붙일 프리앰블 문자열로 포매팅한다.
"""history_to_preamble([{role, content}]) → '[이전 대화]…[현재 질문]\n' 또는 ''(빈 히스토리)."""

from __future__ import annotations

_ROLE_LABEL = {"user": "사용자", "assistant": "어시스턴트"}


def history_to_preamble(history: list[dict] | None) -> str:
    """히스토리를 한국어 프리앰블로. 비어 있으면 빈 문자열(1턴 동작 불변)."""
    if not history:
        return ""
    lines: list[str] = []
    for h in history:
        content = (h.get("content") or "").strip()
        if not content:
            continue
        label = _ROLE_LABEL.get(h.get("role"), h.get("role") or "")
        lines.append(f"{label}: {content}")
    if not lines:
        return ""
    return "[이전 대화]\n" + "\n".join(lines) + "\n\n[현재 질문]\n"
