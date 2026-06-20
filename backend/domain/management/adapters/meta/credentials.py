# 🅰 멀티테넌트 Meta 자격증명 심 — settings(.env 단일 토큰) ↔ 테넌트별 토큰의 단일 해석 지점
from __future__ import annotations

from dataclasses import dataclass

from domain.management.adapters.meta.client import mask_token


@dataclass(frozen=True)
class MetaCredentials:
    """build_meta_client이 settings에서 읽던 속성을 그대로 노출하는 자격증명 묶음.

    속성 이름을 settings와 동일하게 둬(meta_access_token 등) build_meta_client에 settings
    대신 그대로 넘길 수 있다(덕타이핑 드롭인). 토큰·시크릿은 평문 로그 금지 대상이라 repr에서
    마스킹한다.
    """

    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_graph_api_version: str | None = None
    meta_app_id: str | None = None
    meta_app_secret: str | None = None

    def __repr__(self) -> str:  # 토큰·시크릿 평문 노출 방지
        return (
            f"MetaCredentials(token={mask_token(self.meta_access_token)}, "
            f"ad_account_id={self.meta_ad_account_id}, "
            f"app_secret={mask_token(self.meta_app_secret)})"
        )


def load_meta_credentials(settings: object, organization_id: str | None = None) -> MetaCredentials:
    """현재 요청의 Meta 자격증명을 해석한다.

    지금은 전역 settings(.env 단일 토큰)에서 채우는 폴백만 구현 — 단일 테넌트·발표 경로를 그대로
    유지한다. organization_id별 암호화 connection 로드는 (A) meta_connections 테이블 도입 후
    이 함수만 교체하면 된다(호출부 불변). org가 와도 아직은 전역 settings로 폴백한다.
    """
    return MetaCredentials(
        meta_access_token=getattr(settings, "meta_access_token", None),
        meta_ad_account_id=getattr(settings, "meta_ad_account_id", None),
        meta_graph_api_version=getattr(settings, "meta_graph_api_version", None),
        meta_app_id=getattr(settings, "meta_app_id", None),
        meta_app_secret=getattr(settings, "meta_app_secret", None),
    )
