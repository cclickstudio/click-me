# Cognito User Pool 관리자 작업 래퍼 — cognito 모드에서 계정 생성/비번/삭제를 DB와 동기화
"""계정 생성·비밀번호 재설정·삭제 시 DB와 Cognito를 함께 맞추기 위한 헬퍼.

auth_provider=local 이면 모든 함수가 no-op(기존 동작 불변). cognito 모드에서만 boto3로
Cognito User Pool을 갱신한다. boto3는 동기라 asyncio.to_thread로 감싸 이벤트 루프를 막지 않는다.
매핑 규약: Cognito username = login_id, role → 동명 그룹(ADMIN/COMPANY/USER).
"""

import asyncio
import contextlib

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import HTTPException

from core.config import settings

_GROUPS = {"ADMIN", "COMPANY", "USER"}


def is_enabled() -> bool:
    """cognito 모드일 때만 Cognito 동기화 수행(local 모드는 no-op)."""
    return settings.auth_provider == "cognito"


def _client() -> BaseClient:
    return boto3.client("cognito-idp", region_name=settings.cognito_region or settings.aws_region)


def _msg(err: Exception) -> str:
    if isinstance(err, ClientError):
        return err.response["Error"].get("Message", err.response["Error"]["Code"])
    return str(err)


def _create_sync(login_id: str, password: str, role: str) -> None:
    pool = settings.cognito_user_pool_id
    client = _client()
    try:
        client.admin_create_user(UserPoolId=pool, Username=login_id, MessageAction="SUPPRESS")
    except ClientError as err:
        # 이미 있으면(예: 부분 실패 후 재시도) 비번·그룹만 다시 맞춘다.
        if err.response["Error"]["Code"] != "UsernameExistsException":
            raise
    client.admin_set_user_password(
        UserPoolId=pool, Username=login_id, Password=password, Permanent=True
    )
    group = role if role in _GROUPS else "USER"
    # 그룹 매핑 실패는 비치명(role 권위는 DB).
    with contextlib.suppress(ClientError):
        client.admin_add_user_to_group(UserPoolId=pool, Username=login_id, GroupName=group)


async def create_user(login_id: str, password: str, role: str) -> None:
    """Cognito에 사용자 생성 + 영구 비번 + role 그룹. 실패 시 502(호출 라우터에서 DB 롤백)."""
    if not is_enabled():
        return
    try:
        await asyncio.to_thread(_create_sync, login_id, password, role)
    except (ClientError, BotoCoreError) as err:
        raise HTTPException(status_code=502, detail=f"Cognito 계정 생성 실패: {_msg(err)}") from err


def _set_password_sync(login_id: str, password: str) -> None:
    _client().admin_set_user_password(
        UserPoolId=settings.cognito_user_pool_id,
        Username=login_id,
        Password=password,
        Permanent=True,
    )


async def set_password(login_id: str, password: str) -> None:
    """Cognito 비밀번호 재설정. 실패 시 502(DB 변경도 롤백돼 비번 불일치 방지)."""
    if not is_enabled():
        return
    try:
        await asyncio.to_thread(_set_password_sync, login_id, password)
    except (ClientError, BotoCoreError) as err:
        raise HTTPException(
            status_code=502, detail=f"Cognito 비밀번호 변경 실패: {_msg(err)}"
        ) from err


def _delete_sync(login_id: str) -> None:
    try:
        _client().admin_delete_user(UserPoolId=settings.cognito_user_pool_id, Username=login_id)
    except ClientError as err:
        if err.response["Error"]["Code"] != "UserNotFoundException":
            raise


async def delete_user(login_id: str) -> bool:
    """삭제는 best-effort — 실패해도 예외를 올리지 않는다(DB는 이미 정리됨). 성공 여부만 반환."""
    if not is_enabled():
        return False
    try:
        await asyncio.to_thread(_delete_sync, login_id)
        return True
    except (ClientError, BotoCoreError):
        return False
