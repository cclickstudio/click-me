# .env 토큰으로 org Meta 연결 행을 직접 심는 시드 스크립트 (OAuth 없이 from-candidate 409 해제용)
"""meta_connections에 org 1건을 upsert한다 — OAuth UI 대신 .env의 토큰·광고계정을 그대로 등록.

실제 콜백(meta_callback)과 동일한 저장소(MetaConnectionRepository) + 동일 암호화(TokenCipher)를
쓴다. writer는 어차피 .env의 META_ACCESS_TOKEN으로 인증하므로, 이 행은 409 게이트 통과 +
ad_account_id 제공용이다(ad_account_id는 META_AD_ACCOUNT_ID와 일치시킨다).

실행:
  cd backend && uv run python scripts/seed_meta_connection.py --login <COMPANY 계정 login_id>
  cd backend && uv run python scripts/seed_meta_connection.py --org-id <org UUID>
  (둘 다 생략하면 org 목록만 출력하고 종료)
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from sqlalchemy import select

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import Organization, OrganizationMember, User
from domain.management.adapters.meta.connection_repository import MetaConnectionRepository
from domain.management.adapters.meta.token_crypto import TokenCipher


async def _resolve_org(db, org_id: str | None, login: str | None) -> uuid.UUID:
    if org_id:
        return uuid.UUID(org_id)
    if login:
        user = await db.scalar(select(User).where(User.login_id == login))
        if user is None:
            raise SystemExit(f"login_id '{login}' 사용자를 찾을 수 없습니다.")
        oid = await db.scalar(
            select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
        )
        if oid is None:
            raise SystemExit(f"'{login}'은 조직 멤버십이 없습니다 (COMPANY 계정인지 확인).")
        return oid
    rows = (await db.execute(select(Organization.id, Organization.name))).all()
    print("org 목록 (--org-id 또는 --login 으로 지정하세요):")
    for oid, name in rows:
        print(f"  {oid}  {name}")
    raise SystemExit(0)


async def main() -> None:
    ap = argparse.ArgumentParser(description="org Meta 연결 시드")
    ap.add_argument("--org-id", help="대상 조직 UUID")
    ap.add_argument("--login", help="대상 COMPANY 계정 login_id (org 자동 해석)")
    args = ap.parse_args()

    key = settings.meta_token_encryption_key
    token = settings.meta_access_token
    ad_account = settings.meta_ad_account_id
    page_id = settings.meta_page_id
    if not key:
        raise SystemExit("META_TOKEN_ENCRYPTION_KEY 미설정 — .env 확인.")
    if not token:
        raise SystemExit("META_ACCESS_TOKEN 미설정 — .env 확인.")
    if not ad_account:
        raise SystemExit("META_AD_ACCOUNT_ID 미설정 — .env 확인.")

    async with AsyncSessionLocal() as db:
        org_id = await _resolve_org(db, args.org_id, args.login)
        repo = MetaConnectionRepository(db, TokenCipher.from_base64_key(key))
        row = await repo.upsert(
            org_id,
            access_token=token,
            ad_account_id=ad_account,
            page_id=page_id,
            scopes=["ads_management", "ads_read"],
        )
        await db.commit()
        print(
            f"✓ 연결 저장 완료 — org={org_id} ad_account={row.ad_account_id} "
            f"page={row.page_id or '(없음)'}"
        )
        print("이제 from-candidate의 409(연결 게이트)가 풀립니다.")


if __name__ == "__main__":
    asyncio.run(main())
