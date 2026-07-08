# 이미지 provider 디스패처 — 작업별 provider(openai/google_genai) SDK 호출 라우팅
"""작업 단위 이미지 모델 스위칭의 실행 계층.

- generate: 0부터 배경 이미지 생성 (openai images.generate / google_genai Gemini·Imagen)
- edit: 기존 이미지를 마스크 없이 편집 (openai images.edit; 그 외 NotImplementedError)
- edit_with_mask: 마스크 인페인팅 — 상품 픽셀 잠금 (openai images.edit; 그 외 NotImplementedError)
- remove_background: 누끼(투명 알파) (openai images.edit background=transparent; 그 외 NotImplementedError)

provider/model/quality는 호출자가 작업별 설정에서 골라 넘긴다.
프롬프트 조립은 호출자 책임 — 여기는 provider에 맞는 SDK 호출만 담당한다.
"""

from __future__ import annotations

import base64
import io
import logging
from typing import Any

from google import genai
from google.genai import types as genai_types
from langsmith import get_current_run_tree
from langsmith.wrappers import wrap_openai
from openai import AsyncOpenAI

from core.config import settings
from core.tracing import record_image_cost
from domain.generator.contracts.enums import AdSize

logger = logging.getLogger("clickme")


def _require_openai_for(op: str, provider: str, model: str) -> str:
    """편집·마스크·누끼는 openai 전용 op다. 다른 provider가 설정되면 openai 키가 있을 때
    모델도 openai 호환 모델로 바꿔 경고 후 openai로 폴백(파이프라인이 죽지 않게),
    키도 없으면 명확히 실패한다. 반환값은 실제로 사용할 모델명이다.

    현실적 오설정 예: generator_image_provider=google_genai → inpaint_provider도 그걸 상속해
    edit_with_mask가 죽는 컴포즈(누끼) 경로. openai 키만 있으면 openai 모델로 바꿔 그대로
    진행시킨다(model을 안 바꾸면 provider의 모델명이 그대로 openai API로 넘어가 오류 남).
    """
    if provider == "openai":
        return model
    if settings.openai_api_key:
        fallback_model = settings.generator_image_edit_model
        logger.warning(
            "%s: provider=%r 미지원 op → openai(%s)로 폴백(설정 확인 권장)",
            op,
            provider,
            fallback_model,
        )
        return fallback_model
    raise NotImplementedError(
        f"{op} 미지원 provider: {provider!r} — openai만 지원하며 OPENAI_API_KEY도 없어 폴백 불가"
    )


# wrap_openai로 감싸 이미지 호출의 토큰·비용 usage가 LangSmith에 기록되게 한다.
# 키는 settings(.env)에서 명시 — os.environ엔 OPENAI_API_KEY가 없어 무인자 생성은 실패한다.
_openai_client = wrap_openai(
    AsyncOpenAI(api_key=settings.openai_api_key, timeout=settings.generator_image_timeout)
)

_GEMINI_NATIVE_ASPECT_RATIO: dict[AdSize, str] = {
    AdSize.SQUARE: "1:1",
    AdSize.LANDSCAPE: "3:2",
    AdSize.PORTRAIT: "2:3",
}

# Imagen은 "1:1"/"3:4"/"4:3"/"9:16"/"16:9"만 지원 — AdSize 비율에 가장 가까운 값으로 매핑
_IMAGEN_ASPECT_RATIO: dict[AdSize, str] = {
    AdSize.SQUARE: "1:1",
    AdSize.LANDSCAPE: "4:3",
    AdSize.PORTRAIT: "3:4",
}

# 누끼 프롬프트 — 상품만 남기고 배경 제거(투명). 고정문이라 디스패처가 보유.
_REMOVE_BG_PROMPT = (
    "Remove the background completely and keep ONLY the main product, "
    "fully preserving its exact shape, colors, text, and details. "
    "Output the product on a fully transparent background. "
    "Do not add, redraw, or stylize anything — keep the product identical to the input."
)


# ── 공개 디스패처 ────────────────────────────────────────────────────────────
async def generate(prompt: str, size: AdSize, *, provider: str, model: str, quality: str) -> bytes:
    """배경 이미지를 0부터 생성. provider=openai|google_genai."""
    if provider == "openai":
        return await _openai_generate(prompt, size, model, quality)
    if provider == "google_genai":
        return await _genai_generate(prompt, size, model)
    raise NotImplementedError(f"지원하지 않는 이미지 provider: {provider!r}")


async def edit(
    image_bytes: bytes, prompt: str, size: AdSize, *, provider: str, model: str
) -> bytes:
    """기존 이미지를 마스크 없이 편집. openai 전용 op — 타 provider는 openai로 폴백."""
    model = _require_openai_for("이미지 편집", provider, model)
    image_file = io.BytesIO(image_bytes)
    image_file.name = "original.png"
    response = await _openai_client.images.edit(
        model=model, image=image_file, prompt=prompt, n=1, size=size.value
    )
    record_image_cost(model=model, size=size.value)
    return base64.b64decode(response.data[0].b64_json)


async def edit_with_mask(
    base_png: bytes, mask_png: bytes, prompt: str, size: AdSize, *, provider: str, model: str
) -> bytes:
    """마스크 인페인팅 — 마스크 투명영역만 재생성, 나머지(상품) 잠금. openai 전용 op(명시 마스크)."""
    model = _require_openai_for("인페인팅", provider, model)
    base_file = io.BytesIO(base_png)
    base_file.name = "base.png"
    mask_file = io.BytesIO(mask_png)
    mask_file.name = "mask.png"
    response = await _openai_client.images.edit(
        model=model, image=base_file, mask=mask_file, prompt=prompt, n=1, size=size.value
    )
    record_image_cost(model=model, size=size.value)
    return base64.b64decode(response.data[0].b64_json)


async def remove_background(
    image_bytes: bytes, *, provider: str, model: str, quality: str
) -> bytes:
    """배경 제거 → 투명 알파 PNG. openai 전용 op(transparent 지원) — 타 provider는 openai로 폴백."""
    model = _require_openai_for("누끼", provider, model)
    image_file = io.BytesIO(image_bytes)
    image_file.name = "product.png"
    kwargs: dict = {
        "model": model,
        "image": image_file,
        "prompt": _REMOVE_BG_PROMPT,
        "n": 1,
        "background": "transparent",
    }
    # gpt-image 계열은 quality를 무시 — 그 외 모델에만 전달(폴백 설정 호환)
    if not model.startswith("gpt-image"):
        kwargs["quality"] = quality
    response = await _openai_client.images.edit(**kwargs)
    # 누끼는 입력 크기를 따라 출력 — 정확 size 미상, 단가는 기본(1024²) 근사.
    record_image_cost(model=model, quality=quality)
    return base64.b64decode(response.data[0].b64_json)


# ── openai ────────────────────────────────────────────────────────────────────
async def _openai_generate(prompt: str, size: AdSize, model: str, quality: str) -> bytes:
    kwargs: dict = {"model": model, "prompt": prompt, "n": 1, "size": size.value}
    # gpt-image-1은 response_format 파라미터를 지원하지 않음 (항상 b64_json 반환)
    if not model.startswith("gpt-image"):
        kwargs["response_format"] = "b64_json"
        kwargs["quality"] = quality
    response = await _openai_client.images.generate(**kwargs)
    record_image_cost(model=model, size=size.value, quality=quality)
    return base64.b64decode(response.data[0].b64_json)


# ── google_genai ──────────────────────────────────────────────────────────────
def _record_genai_usage(resp: Any, model: str) -> None:
    """google-genai 직접 호출(genai SDK)의 토큰·모델명을 현재 LangSmith run에 기록.

    LangChain/wrap_openai를 거치지 않는 호출은 토큰·비용이 자동 집계되지 않으므로 수동 주입한다
    (docs/langsmith-guide.md §7 표준 패턴). 이미지 전용 모델(Imagen 등)은 usage_metadata가 없을 수
    있어 모델명(ls_model_name)만이라도 남겨 비용 계산·필터가 가능하게 한다. 트레이싱 OFF면 무동작.
    """
    run = get_current_run_tree()
    if run is None:
        return
    meta = {"ls_model_name": model, "ls_provider": "google_genai"}
    um = getattr(resp, "usage_metadata", None)
    if um is None:
        run.set(metadata=meta)
        return
    run.set(
        usage_metadata={
            "input_tokens": getattr(um, "prompt_token_count", None) or 0,
            "output_tokens": getattr(um, "candidates_token_count", None) or 0,
            "total_tokens": getattr(um, "total_token_count", None) or 0,
        },
        metadata=meta,
    )


async def _genai_generate(prompt: str, size: AdSize, model: str) -> bytes:
    if model.startswith("imagen-"):
        return await _genai_imagen(model, prompt, size)
    return await _genai_native(model, prompt, size)


async def _genai_native(model: str, prompt: str, size: AdSize) -> bytes:
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=genai_types.ImageConfig(aspect_ratio=_GEMINI_NATIVE_ASPECT_RATIO[size]),
        ),
    )
    _record_genai_usage(response, model)
    _um = getattr(response, "usage_metadata", None)
    record_image_cost(model=model, tokens=getattr(_um, "total_token_count", None) if _um else None)
    if not response.candidates:
        raise RuntimeError("Gemini 응답에 candidates가 없음")
    for part in response.candidates[0].content.parts:
        if part.inline_data and part.inline_data.data:
            return part.inline_data.data
    raise RuntimeError("Gemini 응답에 이미지 데이터가 없음")


async def _genai_imagen(model: str, prompt: str, size: AdSize) -> bytes:
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_images(
        model=model,
        prompt=prompt,
        config=genai_types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio=_IMAGEN_ASPECT_RATIO[size],
        ),
    )
    _record_genai_usage(response, model)
    if not response.generated_images:
        raise RuntimeError("Imagen 응답에 이미지가 없음")
    return response.generated_images[0].image.image_bytes
