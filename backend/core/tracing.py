# LangSmith RunnableConfig 조립 헬퍼 — 팀 공통 Trace 이름·Metadata·Tags 표준화
from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from core.config import settings


def make_trace_config(
    *,
    domain: str,
    feature: str,
    mode: str | None = None,
    user_id: str = "anonymous",
    ad_id: str | None = None,
    project_id: str | None = None,
    extra_metadata: dict | None = None,
    extra_tags: list[str] | None = None,
    configurable: dict | None = None,
) -> RunnableConfig:
    """LangSmith 표준 RunnableConfig를 조립한다.

    run_name 형식: {domain}.{feature}[.{mode}]
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
