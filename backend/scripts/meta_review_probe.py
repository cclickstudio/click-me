"""App Review 권한 커버리지 프로브 — 이용 사례별 '필요한 API 호출 0/1개'를 채운다.

각 권한이 요구하는 대표 엔드포인트를 1회씩 실제 호출해 권한을 '테스트됨'으로 만든다.
(meta_warmup.py 는 등급 상향용 500콜 볼륨 전용 — 역할 분리.)

실행:  cd backend && uv run python scripts/meta_review_probe.py
.env:  META_ACCESS_TOKEN · META_PAGE_ID · META_BUSINESS_ID · META_AD_ACCOUNT_ID · META_IG_USER_ID

참고: instagram_content_publish(게시)·instagram_business_manage_messages(DM)는
GET로 검증 불가 — 실제 게시/메시지 액션이 있어야 테스트됨(콘솔/수동).
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from core.config import settings
from domain.management.adapters.meta.client import MetaApiError, MetaClient, build_meta_client


async def _probe(client: MetaClient, perm: str, path: str, params: dict) -> bool:
    try:
        await client.get(path, params)
        print(f"  OK    {perm:30} {path}", flush=True)
        return True
    except MetaApiError as exc:
        print(f"  FAIL  {perm:30} {path}\n        {str(exc)[:160]}", flush=True)
        return False


async def run() -> None:
    client = build_meta_client(settings)
    page = settings.meta_page_id
    biz = settings.meta_business_id
    acct = settings.meta_ad_account_id
    ig = settings.meta_instagram_account_id

    # 페이지 레벨 읽기는 페이지 토큰이 필요 — 시스템유저 토큰으로 발급받아 주입
    page_token: dict[str, str] = {}
    if page:
        try:
            p = await client.get(page, {"fields": "access_token"})
            if p.get("access_token"):
                page_token = {"access_token": p["access_token"]}
        except MetaApiError as exc:
            print(f"  (페이지 토큰 조회 실패: {str(exc)[:120]})", flush=True)

    checks: list[tuple[str, str, dict]] = [
        ("public_profile", "me", {"fields": "id,name"}),
        ("pages_show_list", "me/accounts", {"fields": "id,name"}),
        ("business_management", biz or "me/businesses", {"fields": "id,name"}),
        ("ads_read", f"{acct}/insights", {"fields": "impressions,spend"}),
        ("ads_management", f"{acct}/campaigns", {"fields": "id,status", "limit": 1}),
        ("pages_read_engagement", f"{page}/posts", {"fields": "id", "limit": 1, **page_token}),
        ("pages_read_user_content", f"{page}/feed", {"fields": "id", "limit": 1, **page_token}),
        (
            "read_insights",
            f"{page}/insights",
            {"metric": "page_post_engagements", "period": "day", **page_token},
        ),
        ("instagram_basic", ig or "", {"fields": "username,media_count"}),
        (
            "instagram_manage_insights",
            f"{ig}/insights",
            {"metric": "reach", "period": "day", "metric_type": "total_value"},
        ),
    ]

    print(f"권한 커버리지 프로브 · API {settings.meta_graph_api_version}", flush=True)
    ok = fail = 0
    for perm, path, params in checks:
        if not path or path.startswith("/") or path.startswith("None"):
            print(f"  SKIP  {perm:30} (필수 ID 미설정)", flush=True)
            continue
        if await _probe(client, perm, path, params):
            ok += 1
        else:
            fail += 1

    print(f"\n완료: 성공 {ok} / 실패 {fail}", flush=True)
    print("→ App Review 화면에서 권한별 '1/1개' 갱신 확인 (집계 지연 가능)", flush=True)
    print("※ instagram_content_publish·메시지 권한은 실제 게시/DM 액션 필요(GET 불가)", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
