# 4-a 프로필 서사 생성 — 실 Gemini 어댑터(google-generativeai). 속성 묶음 → 한국어 인물 서사.
#
# 원칙: LLM은 "주어진 속성을 말로 풀어주기만" 한다. 새 속성 생성 금지(동질화 원인).
# core.config 미의존(현재 backend/.env 부재로 깨짐) — 키는 os.environ 또는 생성자 주입.
from __future__ import annotations

import os

from domain.simulation.contracts.schemas import Persona

# 재현성 위해 고정 버전 핀(alias -latest 회피). gemini-2.0-flash 는 퇴역.
_DEFAULT_MODEL = "gemini-2.5-flash"


def _build_prompt(persona: Persona) -> str:
    return (
        "다음은 통계적으로 샘플링된 한국 소비자 한 명의 속성이다. "
        "이 속성들을 자연스러운 한국어 인물 소개 2~3문장으로 풀어라. "
        "**주어진 속성만 사용**하고, 새로운 나이·성별·직업·소비 성향을 지어내지 마라.\n\n"
        f"- 나이: {persona.age}\n"
        f"- 성별: {persona.gender}\n"
        f"- 지역: {persona.region}\n"
        f"- OCEAN(표준화 점수, 양수=평균이상/음수=평균이하): {persona.ocean}\n"
        f"- 미디어 행동: {persona.media_behavior}\n"
        f"- 보유 소비가치: {[k for k, v in persona.consumption_values.items() if v]}\n"
    )


class GeminiNarrator:
    """Gemini 2.0 Flash 로 4-a 서사 생성. 빌드 시 1회 호출(런타임 아님)."""

    def __init__(self, *, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        import google.generativeai as genai

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY 미설정 — 서사 생성 불가")
        genai.configure(api_key=key)
        self.version = model
        self._model = genai.GenerativeModel(model)

    def narrate(self, persona: Persona) -> str:
        resp = self._model.generate_content(_build_prompt(persona))
        return (getattr(resp, "text", "") or "").strip()
