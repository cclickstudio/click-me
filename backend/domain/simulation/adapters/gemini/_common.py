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
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

_DEFAULT_MODEL = "gemini-2.5-flash"  # 재현성 위해 버전 핀

# Gemini 503(과부하)·429·5xx·네트워크 일시 오류 재시도 — 서버 과부하는 백오프로 대부분 복구된다.
# (테스트는 _RETRY_WAIT_* 를 0으로 몽키패치해 무대기로 검증)
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_RETRY_ATTEMPTS = 5
_RETRY_WAIT_MULTIPLIER = 1.0
_RETRY_WAIT_MAX = 30.0


def _use_openai() -> bool:
    """시뮬 LLM 공급자 전환 — SIMULATION_LLM_PROVIDER=openai면 Gemini 대신 OpenAI를 1차로 쓴다."""
    return os.environ.get("SIMULATION_LLM_PROVIDER", "gemini").lower() == "openai"


def _is_transient(exc: BaseException) -> bool:
    """일시 오류(재시도 대상)인가 — 503/429/5xx·네트워크. 안전블록·4xx(429 제외)는 비대상."""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int) and code in _RETRY_STATUS:
        return True
    text = f"{type(exc).__name__} {exc}".lower()
    return any(
        k in text
        for k in (
            "unavailable",
            "overloaded",
            "503",
            "502",
            "504",
            # OpenAI SDK 일시 오류(상태코드 없는 연결·타임아웃) 클래스명 매칭
            "apiconnection",
            "apitimeout",
            "internalservererror",
        )
    )


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


async def _openai_json_fallback(contents: Any, temperature: float | None) -> dict:
    """Gemini 일시 장애(503 등) 시 OpenAI로 동일 JSON 생성 — 텍스트+이미지(비전) 지원.

    contents의 str은 텍스트로, google-genai Part(inline 이미지)는 data URL로 변환해 보낸다.
    OPENAI_API_KEY 없으면 RuntimeError(원오류 재전파는 호출부에서).
    """
    import base64
    import logging

    from openai import AsyncOpenAI

    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY 미설정 — Gemini JSON 폴백 불가")
    parts = contents if isinstance(contents, list) else [contents]
    user_content: list[dict] = []
    for p in parts:
        if isinstance(p, str):
            user_content.append({"type": "text", "text": p})
            continue
        inline = getattr(p, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            mime = getattr(inline, "mime_type", None) or "image/jpeg"
            b64 = base64.b64encode(inline.data).decode()
            user_content.append(
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
            )
    model = os.environ.get("SIMULATION_OPENAI_JSON_MODEL", "gpt-4.1-mini")
    resp = await AsyncOpenAI(api_key=key).chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Respond with a single valid JSON object only."},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.0 if temperature is None else temperature,
    )
    logging.getLogger("clickme").info("Gemini→OpenAI JSON 폴백 성공(model=%s)", model)
    return _parse_json(resp.choices[0].message.content or "")


@traceable(run_type="llm", name="gemini.generate_content", process_inputs=_trace_inputs)
async def _agen_json(
    client: Any, model: str, contents: Any, *, temperature: float | None = None
) -> dict:
    """google-genai 비동기 호출 + JSON 파싱. contents는 str 또는 [str, 이미지 Part] 리스트.

    Gemini가 일시 장애(503 등)면 OpenAI로 폴백(키 있을 때). LangSmith LLM run으로 추적.
    공급자 전환(SIMULATION_LLM_PROVIDER=openai)이면 Gemini를 건너뛰고 바로 OpenAI로 생성한다.
    """
    if _use_openai():
        return await _openai_json_fallback(contents, temperature)
    # 과부하(503) 우회용 모델 교체 — SIMULATION_GEMINI_MODEL 설정 시 그 모델로(미설정이면 핀 유지).
    model = os.environ.get("SIMULATION_GEMINI_MODEL") or model
    config: dict[str, Any] = {"response_mime_type": "application/json"}
    if temperature is not None:
        config["temperature"] = temperature
    # OpenAI 폴백이 가능하면 Gemini 재시도를 짧게(2회) 하고 빨리 폴백 — 없으면 끝까지 재시도.
    has_fallback = bool(os.environ.get("OPENAI_API_KEY"))
    attempts = 2 if has_fallback else _RETRY_ATTEMPTS
    resp = None
    try:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception(_is_transient),
            wait=wait_random_exponential(multiplier=_RETRY_WAIT_MULTIPLIER, max=_RETRY_WAIT_MAX),
            stop=stop_after_attempt(attempts),
            reraise=True,
        ):
            with attempt:
                resp = await client.aio.models.generate_content(
                    model=model, contents=contents, config=config
                )
    except Exception as exc:
        # Gemini 일시 장애 → OpenAI로 동일 JSON 생성(폴백). 영속 오류(파싱 등)는 그대로 전파.
        if has_fallback and _is_transient(exc):
            return await _openai_json_fallback(contents, temperature)
        raise
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
