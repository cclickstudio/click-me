# Gemini 어댑터 공통 — 클라이언트 생성·async 호출·이미지 로드·JSON 파싱(google-genai).
#
# 어댑터들이 공유하는 LLM 호출 인프라. core.config 미의존(키 주입), 모델 버전 핀.
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from langsmith import get_current_run_tree, traceable

_DEFAULT_MODEL = "gemini-2.5-flash"  # 재현성 위해 버전 핀


def _enum_values(enum_cls) -> str:
    return ", ".join(e.value for e in enum_cls)


def _trace_inputs(inputs: dict) -> dict:
    # client(genai.Client)는 직렬화 의미가 없음 → 트레이스 입력에서 제거, 모델·프롬프트만 남긴다.
    return {k: v for k, v in inputs.items() if k != "client"}


def _record_usage(resp: Any, model: str) -> None:
    """google-genai 응답의 토큰 사용량을 현재 LangSmith run에 기록(트레이싱 OFF면 무동작)."""
    run = get_current_run_tree()
    um = getattr(resp, "usage_metadata", None)
    if run is None or um is None:
        return
    run.set(
        usage_metadata={
            "input_tokens": getattr(um, "prompt_token_count", None) or 0,
            "output_tokens": getattr(um, "candidates_token_count", None) or 0,
            "total_tokens": getattr(um, "total_token_count", None) or 0,
        },
        metadata={"ls_model_name": model, "ls_provider": "google_genai"},
    )


def _new_client(api_key: str | None) -> Any:
    from google import genai

    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY 미설정 — 실 LLM 어댑터 불가")
    return genai.Client(api_key=key)


@traceable(run_type="llm", name="gemini.generate_content", process_inputs=_trace_inputs)
async def _agen_json(
    client: Any, model: str, contents: Any, *, temperature: float | None = None
) -> dict:
    """google-genai 비동기 호출 + JSON 파싱. contents는 str 또는 [str, 이미지 Part] 리스트.

    LangSmith LLM run으로 추적 — 응답 토큰량(usage_metadata)을 현재 run에 첨부한다.
    """
    config: dict[str, Any] = {"response_mime_type": "application/json"}
    if temperature is not None:
        config["temperature"] = temperature
    resp = await client.aio.models.generate_content(model=model, contents=contents, config=config)
    _record_usage(resp, model)
    return _parse_json(getattr(resp, "text", "") or "")


async def _load_image(url: str) -> tuple[bytes, str]:
    """광고 이미지 로드 → (bytes, mime). http(s)는 httpx, 그 외는 로컬 경로."""
    if url.startswith(("http://", "https://")):
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(url)
            r.raise_for_status()
            mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0]
            return r.content, mime
    data = Path(url).read_bytes()
    return data, (mimetypes.guess_type(url)[0] or "image/jpeg")


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출 — 코드펜스 제거 후 파싱."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        t = t[4:].strip() if t.lower().startswith("json") else t.strip()
    return json.loads(t)
