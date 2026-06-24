# CLIO general 핸들러 — Gemini 2.5-flash 답변(키 없으면 None → 결정론 폴백).
"""general 라우트용. 그래프 synthesize가 주입받아 호출.

두 가지 호출면을 노출한다.
- `await clio(text, history)` → 전체 답변(비스트리밍, 하위호환).
- `async for piece in clio.stream(text, history)` → 토큰 조각(진짜 스트리밍).
synthesize가 stream을 우선 사용해 토큰을 흘리고, 미지원이면 전체 호출로 폴백한다.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

# chat.py에서 이관한 CLIO 시스템 프롬프트(verbatim).
_CLIO_SYSTEM = """\
당신은 ClickMe의 수석 광고 전략 AI 어드바이저 'CLIO'입니다.

## 정체성
10년 경력의 디지털 마케팅 전문가로, KOBACO 광고 효과 지수 분석과 소비자 행동 심리(OCEAN 모델)에 정통합니다.
데이터 기반 인사이트를 마케터의 언어로 풀어내며, 숫자 뒤에 숨겨진 소비자 심리를 읽어내는 것이 특기입니다.

## 전문 영역
- 광고 시뮬레이션 결과 해석 (구매의향 분포, CTR/CVR 예측)
- 타겟 세그먼트별 메시지 전략 수립
- 한국 광고 시장 트렌드 및 KOBACO 기준선 분석
- 크리에이티브 카피 개선 제안
- A/B 테스트 설계 및 성과 비교

## 응답 스타일
- 핵심 인사이트를 먼저 제시하고, 근거를 간결하게 설명
- 수치를 제시할 때는 비교 기준(업계 평균, KOBACO 기준선)과 함께 언급
- 실행 가능한 제안을 항상 포함
- 한국어로 응답하며, 전문 용어는 자연스럽게 풀어서 설명
"""


class _Clio:
    """Gemini 2.5-flash 기반 CLIO — 비스트리밍 호출 + 토큰 스트리밍 둘 다 제공."""

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    def _model(self) -> object:
        import google.generativeai as genai  # noqa: PLC0415

        genai.configure(api_key=self._key)
        return genai.GenerativeModel(model_name="gemini-2.5-flash", system_instruction=_CLIO_SYSTEM)

    @staticmethod
    def _contents(user_text: str, history: list) -> list[dict]:
        # history: [{role, content}] → Gemini contents 매핑; 마지막 user_text 포함.
        contents: list[dict] = []
        for h in history or []:
            role = "user" if h.get("role") in ("user", "human") else "model"
            contents.append({"role": role, "parts": [h.get("content", "")]})
        contents.append({"role": "user", "parts": [user_text]})
        return contents

    async def __call__(self, user_text: str, history: list) -> str:
        """전체 답변 — generate_content_async, 없으면 to_thread 동기 폴백."""
        import asyncio  # noqa: PLC0415

        model = self._model()
        contents = self._contents(user_text, history)
        if hasattr(model, "generate_content_async"):
            resp = await model.generate_content_async(contents)
        else:
            resp = await asyncio.to_thread(model.generate_content, contents)
        return resp.text or ""

    async def stream(self, user_text: str, history: list) -> AsyncIterator[str]:
        """토큰 조각 — generate_content_async(stream=True)의 청크 텍스트를 yield."""
        model = self._model()
        contents = self._contents(user_text, history)
        resp = await model.generate_content_async(contents, stream=True)
        async for chunk in resp:
            text = getattr(chunk, "text", "") or ""
            if text:
                yield text


def build_clio(settings) -> _Clio | None:
    """gemini_api_key 있으면 _Clio 인스턴스, 없으면 None(결정론 폴백)."""
    key = getattr(settings, "gemini_api_key", None)
    if not key:
        return None
    return _Clio(key)
