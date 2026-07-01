# admin org 스코프 — 헤더 캡처·해석기·검증·전역뷰 테스트
import uuid

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from api.routers import management


@pytest.fixture(autouse=True)
def _reset_org_ctx():
    """각 테스트 전후로 ContextVar 초기화 — 요청 밖 누수/순서 의존 제거."""
    token = management._selected_org_ctx.set(None)
    yield
    management._selected_org_ctx.reset(token)


def test_header_captured_during_and_reset_after():
    """요청 중 헤더를 ContextVar에 캡처하고 요청 후 reset 하는지 (로컬 router로 전역 오염 방지)."""
    seen = {}
    probe = APIRouter(dependencies=[Depends(management._capture_selected_org)])

    @probe.get("/__ctxprobe")
    async def _p():
        seen["during"] = management._selected_org_ctx.get()
        return {"ok": True}

    app = FastAPI()
    app.include_router(probe)
    TestClient(app).get("/__ctxprobe", headers={"X-Org-Id": "org-abc"})
    assert seen["during"] == "org-abc"
    assert management._selected_org_ctx.get() is None  # 요청 후 reset


class _OrgDB:
    """Organization.status 조회만 흉내내는 최소 FakeDB."""

    def __init__(self, status):
        self._status = status

    async def scalar(self, *_a, **_k):
        return self._status


@pytest.mark.asyncio
async def test_validated_org_bad_uuid_400():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB("ACTIVE"), "not-a-uuid", require_active=True)
    assert e.value.status_code == 400


@pytest.mark.asyncio
async def test_validated_org_missing_404():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB(None), str(uuid.uuid4()), require_active=True)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_validated_org_inactive_blocked_for_operational_409():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        await management._validated_org(_OrgDB("SUSPENDED"), str(uuid.uuid4()), require_active=True)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_validated_org_inactive_allowed_for_read():
    org = uuid.uuid4()
    got = await management._validated_org(_OrgDB("SUSPENDED"), str(org), require_active=False)
    assert got == org
