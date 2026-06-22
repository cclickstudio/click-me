# LangSmith RunnableConfig 조립 헬퍼 — 전 도메인 공용 (docs/management LangSmith 가이드 §4)

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
) -> RunnableConfig:
    """LangSmith 표준 run_name·tags·metadata를 담은 RunnableConfig를 만든다.

    run_name = ``{domain}.{feature}[.{mode}]``. tags·metadata는 가이드 §4·§5 표준 키를
    채우고, 도메인별 추가 키는 extra_metadata / extra_tags로 합친다.
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

    return RunnableConfig(run_name=run_name, tags=tags, metadata=metadata)
