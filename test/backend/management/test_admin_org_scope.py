# admin org 스코프 — 헤더 캡처·해석기·검증·전역뷰 테스트
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
