# 챗 오케스트레이터용 generator 도메인 에이전트 — 이미지로 생성 잡을 트리거하고 핸드오프 반환
from __future__ import annotations

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.service.generator_service import start_generation, store_temp_image
from tools.storage.s3 import download_bytes

_DEFAULT_TARGET = "전체"


def _first_image_key(attachments) -> str | None:
    for a in attachments:
        if getattr(a, "kind", None) == "image" and getattr(a, "s3_key", None):
            return a.s3_key
    return None


def _derive_product_name(user_input: str) -> str:
    text = (user_input or "").strip()
    return text[:40] if text else "상품"


class GeneratorDomainAgent:
    """챗 계약 ask(ctx, step) — ctx.attachments의 이미지로 실 생성 잡을 시작(job start까지만)."""

    domain = "generator"

    async def ask(self, ctx, step) -> dict:
        s3_key = _first_image_key(ctx.attachments)
        temp_key = None
        if s3_key:
            data = await download_bytes(s3_key)
            temp_key = await store_temp_image(data)
        # step.inputs.query 우선(Planner가 스텝별로 지정한 값) → 없으면 ctx.user_input → 기본
        desc = (step.inputs.get("query") or ctx.user_input or "").strip() or "상품 광고"
        req = GenerationCreateRequest(
            mode=GenerationMode.CREATE,
            product_description=desc,
            product_name=_derive_product_name(ctx.user_input),
            target_audience=_DEFAULT_TARGET,
            product_image_temp_key=temp_key,
        )
        generation_id = await start_generation(req)
        return {
            "status": "started",
            "step_id": step.id,
            "domain": step.domain,
            "action": step.action,
            "task_id": generation_id,
            "stream_url": f"/api/generator/generations/{generation_id}/stream",
            "ad_id": None,
        }
