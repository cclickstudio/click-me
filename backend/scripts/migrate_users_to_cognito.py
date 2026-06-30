# 기존 DB 사용자를 Cognito User Pool에 일괄 등록하는 마이그레이션 스크립트
"""평문 비밀번호 CSV를 입력받아 DB의 User를 Cognito User Pool에 등록한다 — username = login_id 규약.

bcrypt 해시는 평문 복원이 불가하므로, 운영자가 아는 평문을 CSV로 넘겨 "기존 비밀번호 그대로"
이전한다. role은 DB에서 조회해 동명 그룹(ADMIN/COMPANY/USER)에 매핑한다. 이미 존재하는
username은 비밀번호·그룹만 재설정(idempotent).

입력 CSV: 각 줄 `login_id,password` (헤더 줄 `login_id,password`는 자동 무시).
평문이 들어가므로 이 파일은 절대 커밋하지 말고(스크래치/임시폴더에 두고) 사용 후 삭제할 것.

기본은 DRY-RUN(비밀번호는 가린 채 대상만 미리보기). 실제 반영은 --apply 필요.

실행:
  # dry-run
  cd backend && uv run python scripts/migrate_users_to_cognito.py --passwords <csv>
  # 실제 등록
  cd backend && uv run python scripts/migrate_users_to_cognito.py --passwords <csv> --apply
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select

from core.config import settings
from core.db import AsyncSessionLocal
from core.models import User

GROUPS = {"ADMIN", "COMPANY", "USER"}


def _read_passwords(path: str) -> list[tuple[str, str]]:
    """CSV(login_id,password)를 읽어 (login_id, password) 목록 반환. 헤더·빈 줄 무시."""
    pairs: list[tuple[str, str]] = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue
            login_id, password = row[0].strip(), row[1].strip()
            if not login_id or not password or login_id.lower() == "login_id":
                continue
            pairs.append((login_id, password))
    return pairs


async def _roles_for(login_ids: list[str]) -> dict[str, str]:
    """login_id → role 매핑(그룹 결정용). DB에 없는 login_id는 빠진다."""
    async with AsyncSessionLocal() as db:
        rows = (await db.scalars(select(User).where(User.login_id.in_(login_ids)))).all()
    return {u.login_id: u.role for u in rows}


def migrate(
    creds: list[tuple[str, str]], roles: dict[str, str], apply: bool
) -> list[tuple[str, str, str, str]]:
    pool_id = settings.cognito_user_pool_id
    if not pool_id:
        print("COGNITO_USER_POOL_ID 미설정 — backend/.env 확인", file=sys.stderr)
        sys.exit(1)
    region = settings.cognito_region or settings.aws_region
    client = boto3.client("cognito-idp", region_name=region)

    results: list[tuple[str, str, str, str]] = []
    for login_id, password in creds:
        role = roles.get(login_id)
        if role is None:
            results.append((login_id, "?", "", "건너뜀(DB에 login_id 없음)"))
            continue
        group = role if role in GROUPS else "USER"
        if not apply:
            results.append((login_id, role, group, "예정(dry-run)"))
            continue

        status = "등록"
        try:
            client.admin_create_user(
                UserPoolId=pool_id, Username=login_id, MessageAction="SUPPRESS"
            )
        except ClientError as err:
            code = err.response["Error"]["Code"]
            if code == "UsernameExistsException":
                status = "이미존재(재설정)"
            else:
                results.append((login_id, role, group, f"오류:{code}"))
                continue

        try:
            client.admin_set_user_password(
                UserPoolId=pool_id, Username=login_id, Password=password, Permanent=True
            )
        except ClientError as err:
            results.append((login_id, role, group, f"비번오류:{err.response['Error']['Code']}"))
            continue
        try:
            client.admin_add_user_to_group(UserPoolId=pool_id, Username=login_id, GroupName=group)
        except ClientError as err:
            status += f" / 그룹실패:{err.response['Error']['Code']}"
        results.append((login_id, role, group, status))
    return results


def main() -> None:
    ap = argparse.ArgumentParser(
        description="평문 CSV로 DB 사용자 → Cognito 등록(기존 비밀번호 유지)"
    )
    ap.add_argument("--passwords", required=True, help="login_id,password CSV 경로(커밋 금지)")
    ap.add_argument("--apply", action="store_true", help="실제 등록(미지정 시 dry-run)")
    args = ap.parse_args()

    creds = _read_passwords(args.passwords)
    roles = asyncio.run(_roles_for([lid for lid, _ in creds]))
    mode = "APPLY" if args.apply else "DRY-RUN"
    pool = settings.cognito_user_pool_id or "(미설정)"
    print(f"입력 {len(creds)}명 · Pool {pool} · 모드 {mode} (비밀번호는 출력하지 않음)\n")

    results = migrate(creds, roles, args.apply)
    writer = csv.writer(sys.stdout)
    writer.writerow(["login_id", "role", "group", "status"])
    writer.writerows(results)


if __name__ == "__main__":
    main()
