# 시뮬 LLM 어댑터 공통 — 클라이언트 생성·async 호출·이미지 로드·JSON 파싱(OpenAI gpt-4o-mini).
#
# 어댑터들이 공유하는 LLM 호출 인프라. core.config 미의존(키 주입), 모델 버전 핀.
# 과거 Gemini(google-genai)를 쓰던 자리 — 503(고수요) 회피 위해 OpenAI gpt-4o-mini로 통일.
# 디렉터리·클래스명(Gemini*)은 호환 위해 유지하되 실제 호출은 OpenAI다.
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
from langsmith import get_current_run_tree, traceable

_DEFAULT_MODEL = "gpt-4o-mini"  # 재현성 위해 버전 핀(구 gemini-2.5-flash 대체)


def _enum_values(enum_cls) -> str:
    return ", ".join(e.value for e in enum_cls)


def _trace_inputs(inputs: dict) -> dict:
    # client(AsyncOpenAI)는 직렬화 의미가 없음 → 트레이스 입력에서 제거, 모델·프롬프트만 남긴다.
    return {k: v for k, v in inputs.items() if k != "client"}


def _record_usage(resp: Any, model: str) -> None:
    """OpenAI 응답의 토큰 사용량을 현재 LangSmith run에 기록(트레이싱 OFF면 무동작)."""
    run = get_current_run_tree()
    um = getattr(resp, "usage", None)
    if run is None or um is None:
        return
    run.set(
        usage_metadata={
            "input_tokens": getattr(um, "prompt_tokens", None) or 0,
            "output_tokens": getattr(um, "completion_tokens", None) or 0,
            "total_tokens": getattr(um, "total_tokens", None) or 0,
        },
        metadata={"ls_model_name": model, "ls_provider": "openai"},
    )


def _new_client(api_key: str | None) -> Any:
    from openai import AsyncOpenAI

    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — 실 LLM 어댑터 불가")
    return AsyncOpenAI(api_key=key, timeout=120.0)


# 모든 어댑터가 JSON 객체를 받도록 강제 — response_format=json_object는 메시지에 'json' 토큰을 요구.
_JSON_SYSTEM = {"role": "system", "content": "반드시 유효한 단일 JSON 객체만 출력하라(JSON only)."}


def _build_messages(contents: Any) -> list[dict]:
    """contents(str 또는 [prompt_str, 이미지_part...])를 OpenAI chat messages로 변환."""
    if isinstance(contents, str):
        return [_JSON_SYSTEM, {"role": "user", "content": contents}]
    # 리스트: 첫 항목은 텍스트 프롬프트, 나머지는 이미지 part(OpenAI content dict).
    text = contents[0] if contents else ""
    parts: list[dict] = [{"type": "text", "text": text}]
    parts.extend(c for c in contents[1:] if isinstance(c, dict))
    return [_JSON_SYSTEM, {"role": "user", "content": parts}]


@traceable(run_type="llm", name="openai.chat.completions", process_inputs=_trace_inputs)
async def _agen_json(
    client: Any, model: str, contents: Any, *, temperature: float | None = None
) -> dict:
    """OpenAI 비동기 호출 + JSON 파싱. contents는 str 또는 [str, 이미지 Part] 리스트.

    LangSmith LLM run으로 추적 — 응답 토큰량(usage)을 현재 run에 첨부한다.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": _build_messages(contents),
        "response_format": {"type": "json_object"},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = await client.chat.completions.create(**kwargs)
    _record_usage(resp, model)
    return _parse_json(resp.choices[0].message.content or "")


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


async def _image_part(url: str) -> dict:
    """광고 이미지 → OpenAI 비전 content part(base64 data URL)."""
    data, mime = await _load_image(url)
    b64 = base64.b64encode(data).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출 — 코드펜스 제거 후 파싱."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("```", 2)[1] if "```" in t[3:] else t.strip("`")
        t = t[4:].strip() if t.lower().startswith("json") else t.strip()
    return json.loads(t)
