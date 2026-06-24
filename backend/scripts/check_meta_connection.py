# from-candidate 409(Meta 연결 게이트) 진단 — 로그인 계정의 org에 연결 행이 있는지 그대로 확인
"""_require_ad_account가 보는 조건을 그대로 찍는다 — use_mock / 사용자→org / 그 org의 연결 행.

실행:
  cd backend && uv run python scripts/check_meta_connection.py --login <앱에서 로그인하는 login_id>
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from sqlalchemy import select

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import MetaConnection, OrganizationMember, User


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--login", required=True, help="앱에서 from-candidate 호출 시 로그인한 login_id"
    )
    args = ap.parse_args()

    print(f"use_mock = {getattr(settings, 'use_mock', True)}")
    print(f"management_execution_mode = {getattr(settings, 'management_execution_mode', None)}")
    print(f".env META_AD_ACCOUNT_ID = {settings.meta_ad_account_id!r}")
    print("-" * 50)

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.login_id == args.login))
        if user is None:
            print(f"✗ login_id '{args.login}' 사용자 없음")
            return
        print(f"user: id={user.id} login_id={user.login_id} role={user.role}")

        org_id = await db.scalar(
            select(OrganizationMember.organization_id).where(OrganizationMember.user_id == user.id)
        )
        if org_id is None:
            print(
                "✗ 이 사용자는 조직 멤버십 없음 → '소속 조직이 없습니다' 409 (이 계정으로는 불가)"
            )
            return
        print(f"org_id(로그인 사용자) = {org_id}")

        conn = await db.scalar(
            select(MetaConnection).where(MetaConnection.organization_id == org_id)
        )
        if conn is None:
            print("✗ 이 org에 MetaConnection 행이 없음 → 409 (시드를 다른 org에 했을 가능성)")
        elif not conn.ad_account_id:
            print(f"✗ 연결 행은 있으나 ad_account_id 비어있음 (값={conn.ad_account_id!r}) → 409")
        else:
            print(f"✓ 연결 OK — ad_account_id={conn.ad_account_id} → 409 안 나야 정상")

        # 참고: 연결 행이 있는 모든 org(시드가 어디 들어갔는지 대조)
        rows = (
            await db.execute(select(MetaConnection.organization_id, MetaConnection.ad_account_id))
        ).all()
        print("-" * 50)
        print("연결 행이 있는 org 전체:")
        for oid, acct in rows:
            mark = " ← 로그인 org" if oid == org_id else ""
            print(f"  org={oid} ad_account={acct!r}{mark}")


if __name__ == "__main__":
    asyncio.run(main())
