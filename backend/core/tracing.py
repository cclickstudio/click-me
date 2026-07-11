# LangSmith RunnableConfig 조립 헬퍼 — 전 도메인 공용 (docs/management LangSmith 가이드 §4)
from __future__ import annotations

from langchain_core.runnables import RunnableConfig
from langsmith import get_current_run_tree

from core.config import settings


def make_trace_config(
    *,
    domain: str,
    feature: str,
    mode: str | None = None,
    user_id: str = "anonymous",
    login_id: str | None = None,
    user_name: str | None = None,
    role: str | None = None,
    ad_id: str | None = None,
    project_id: str | None = None,
    extra_metadata: dict | None = None,
    extra_tags: list[str] | None = None,
    configurable: dict | None = None,
) -> RunnableConfig:
    """LangSmith 표준 run_name·tags·metadata를 담은 RunnableConfig를 만든다.

    run_name = ``{domain}.{feature}[.{mode}]``. tags·metadata는 가이드 §4·§5 표준 키를
    채우고, 도메인별 추가 키는 extra_metadata / extra_tags로 합친다.
    login_id·user_name·role: 사용자별 필터·그룹용(사람이 읽는 식별자). user_id는 UUID.
    configurable: LangGraph emit 콜백 등 그래프 내부 전달값.
    """
    run_name = f"{domain}.{feature}" + (f".{mode}" if mode else "")
    tags = [domain, feature, settings.app_env] + (extra_tags or [])
    if mode:
        tags.append(mode)

    metadata: dict = {
        "domain": domain,
        "feature": feature,
        "env": settings.app_env,
        "user_id": user_id,
        "ad_id": ad_id,
        "project_id": project_id,
    }
    # 사람이 읽는 사용자 식별자 — 있을 때만 실어 LangSmith에서 user별 필터/그룹에 쓴다.
    if login_id:
        metadata["login_id"] = login_id
    if user_name:
        metadata["user_name"] = user_name
    if role:
        metadata["role"] = role
    if mode:
        metadata["mode"] = mode
    if extra_metadata:
        metadata.update(extra_metadata)

    return RunnableConfig(
        run_name=run_name,
        tags=tags,
        metadata=metadata,
        configurable=configurable or {},
    )


# ── 이미지 생성 비용 기록 ──────────────────────────────────────────────────────
# LangSmith는 이미지 모델 단가를 자동 계산하지 못해(토큰 기반 텍스트 모델만) 수동으로
# cost_usd를 노드 메타에 싣는다. 단가는 OpenAI/Google 공개가(기준 2026-06, 변동 시 갱신).
# gpt-image 계열: size×quality별 이미지당 USD. gemini image: 이미지당 근사 정액.
_IMAGE_PRICE_USD: dict[str, dict[tuple[str, str], float]] = {
    "gpt-image-1": {
        ("1024x1024", "low"): 0.011,
        ("1024x1024", "medium"): 0.042,
        ("1024x1024", "high"): 0.167,
        ("1024x1536", "low"): 0.016,
        ("1024x1536", "medium"): 0.063,
        ("1024x1536", "high"): 0.25,
        ("1536x1024", "low"): 0.016,
        ("1536x1024", "medium"): 0.063,
        ("1536x1024", "high"): 0.25,
    },
    # gpt-image-2 공개가(기준 2026-07) — 정사각은 gpt-image-1보다 low는 싸고 high는 비쌈.
    "gpt-image-2": {
        ("1024x1024", "low"): 0.006,
        ("1024x1024", "medium"): 0.053,
        ("1024x1024", "high"): 0.211,
        ("1024x1536", "low"): 0.005,
        ("1024x1536", "medium"): 0.041,
        ("1024x1536", "high"): 0.165,
        ("1536x1024", "low"): 0.005,
        ("1536x1024", "medium"): 0.041,
        ("1536x1024", "high"): 0.165,
    },
}
# 토큰 기반(gemini image): 토큰 실측이 있으면 그걸로 계산, 없으면 이미지당 근사 정액.
_GEMINI_IMAGE_USD_PER_1K_TOK = 0.03  # ~$30 / 1M 출력 토큰
_IMAGE_FLAT_USD: dict[str, float] = {
    "gemini-2.5-flash-image": 0.039,  # ~1290 tok/이미지 근사
    "gemini-3-pro-image": 0.134,  # 1K~2K 표준(출처 상이 — Google 공식가로 확정 권장)
}


def _lookup_image_price(model: str, size: str, quality: str) -> float | None:
    """모델·size·quality로 이미지당 USD 조회. 표에 없으면 None."""
    table = _IMAGE_PRICE_USD.get(model)
    if table is None:
        return _IMAGE_FLAT_USD.get(model)
    return table.get((size, quality))


def record_image_cost(
    *,
    model: str,
    size: str | None = None,
    quality: str | None = None,
    n: int = 1,
    tokens: int | None = None,
    operation: str | None = None,
) -> None:
    """현재 트레이스 노드에 이미지 생성 cost_usd를 기록(best-effort).

    gpt-image 계열은 size×quality 단가표로, gemini image는 tokens 실측(있으면) 또는
    정액으로 계산한다. 활성 run이 없으면(트레이싱 off) 조용히 무시한다.
    operation(generate/edit/edit_with_mask/remove_background)과 image_quality를 함께 남겨
    LangSmith에서 모델×품질×작업 단위로 비용을 분해·필터할 수 있게 한다.
    """
    run = get_current_run_tree()
    if run is None:
        return
    size = (size or "1024x1024").lower()
    quality = (quality or "medium").lower()

    if tokens and model not in _IMAGE_PRICE_USD:
        # 토큰 실측이 있는 토큰 기반 이미지 모델(gemini) — 실측으로 계산.
        cost = round(tokens / 1000 * _GEMINI_IMAGE_USD_PER_1K_TOK, 6)
    else:
        unit = _lookup_image_price(model, size, quality)
        cost = round(unit * n, 6) if unit is not None else None

    # 한 노드에서 이미지가 여러 번 생성될 수 있어 cost_usd·image_count를 누적(덮어쓰기 방지).
    prev_meta = (getattr(run, "extra", None) or {}).get("metadata") or {}
    meta: dict = {
        "image_model": model,
        "image_count": (prev_meta.get("image_count") or 0) + n,
        "image_size": size,
        "image_quality": quality,
    }
    if operation is not None:
        meta["operation"] = operation
    if cost is not None:
        meta["cost_usd"] = round((prev_meta.get("cost_usd") or 0) + cost, 6)
    run.set(metadata=meta)
