# 생성 후반 워크플로우 채팅 도구 테스트 — select/publish/render/zip/브랜드키트 (DB 없음)
"""str 반환 도구를 .coroutine으로 직접 호출해 확정·게시 게이트·링크·org 가드를 고정한다.

DB를 타는 조회(list_generations·fetch_generation_result)는 모듈 전역을 monkeypatch로 대체한다
(도구 클로저가 호출 시점에 모듈 전역을 참조하므로 패치가 그대로 먹는다).
"""

import pytest

import api.assistant.subagent_tools as st
from api.assistant.subagent_tools import build_chat_tools
from core.config import settings


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in build_chat_tools(settings)}


def _state(**kw):
    base = {
        "project_id": "p1",
        "session_id": "t",
        "user_id": None,
        "org_id": None,
        "messages": [],
    }
    base.update(kw)
    return base


_DETAIL = {
    "generation_id": "g1",
    "status": "completed",
    "candidate_count": 2,
    "selected_candidate_id": "c2",
    "candidates": [
        {"candidate_id": "c1", "strategy": "benefit", "headline": "헤드1", "qa_passed": True},
        {"candidate_id": "c2", "strategy": "fomo", "headline": "헤드2", "qa_passed": True},
    ],
    "error_message": None,
}


@pytest.fixture
def patched_generation(monkeypatch):
    """최근 완료 생성 g1 + 후보 2개(선택=c2)로 조회 경로를 대체."""

    async def _list(project_id, limit=10):
        return [{"id": "g1", "status": "completed"}]

    async def _fetch(gid):
        return dict(_DETAIL)

    monkeypatch.setattr(st, "list_generations", _list)
    monkeypatch.setattr(st, "fetch_generation_result", _fetch)
    return monkeypatch


@pytest.mark.asyncio
async def test_new_workflow_tools_registered(tools):
    for name in (
        "select_ad_candidate",
        "publish_ad_candidate",
        "render_ad_for_platform",
        "download_generation_zip",
        "list_brand_kits",
        "save_brand_kit",
        "delete_brand_kit",
    ):
        assert name in tools


@pytest.mark.asyncio
async def test_select_without_generations_notice(tools):
    # project_id 없음 → list_generations가 빈 목록(조기 반환) → 안내문
    out = await tools["select_ad_candidate"].coroutine(state=_state(project_id=None))
    assert "완료된 광고 생성이 없어요" in out


@pytest.mark.asyncio
async def test_select_requires_candidate_number(tools, patched_generation):
    out = await tools["select_ad_candidate"].coroutine(state=_state())
    assert "1~2번" in out


@pytest.mark.asyncio
async def test_select_picks_by_number(tools, patched_generation):
    from domain.generator.service import generator_service

    calls = {}

    async def _select(gid, cid):
        calls["args"] = (gid, cid)
        return True

    patched_generation.setattr(generator_service, "select_candidate", _select)
    out = await tools["select_ad_candidate"].coroutine(state=_state(), candidate_number=1)
    assert calls["args"] == ("g1", "c1")
    assert "확정했어요" in out
    assert "benefit" in out


@pytest.mark.asyncio
async def test_publish_gate_asks_confirmation(tools, patched_generation):
    # confirm=False(기본) → 실게시 없이 확인 질문만
    out = await tools["publish_ad_candidate"].coroutine(state=_state(), caption="런칭!")
    assert "게시할까요" in out
    assert "헤드2" in out  # 확정 후보(c2)의 헤드라인


@pytest.mark.asyncio
async def test_publish_requires_selection(tools, patched_generation):
    async def _fetch_unselected(gid):
        return {**_DETAIL, "selected_candidate_id": None}

    patched_generation.setattr(st, "fetch_generation_result", _fetch_unselected)
    out = await tools["publish_ad_candidate"].coroutine(state=_state(), confirm=True)
    assert "먼저 시안을 선택" in out


@pytest.mark.asyncio
async def test_render_rejects_unknown_platform(tools):
    out = await tools["render_ad_for_platform"].coroutine(state=_state(), platform="tiktok")
    assert "지원하는 플랫폼" in out


@pytest.mark.asyncio
async def test_render_returns_url_for_given_candidate(tools):
    out = await tools["render_ad_for_platform"].coroutine(
        state=_state(), platform="ig_story", candidate_id="cX"
    )
    assert "/api/generator/candidates/cX/render?platform=ig_story" in out
    assert "1080x1920" in out


@pytest.mark.asyncio
async def test_zip_returns_download_url(tools, patched_generation):
    out = await tools["download_generation_zip"].coroutine(state=_state())
    assert "/api/generator/generations/g1/download-zip" in out


@pytest.mark.asyncio
async def test_brand_kit_tools_require_org(tools):
    state = _state(org_id=None)
    assert "조직 정보" in await tools["list_brand_kits"].coroutine(state=state)
    assert "조직 정보" in await tools["save_brand_kit"].coroutine(state=state, name="키트")
    assert "조직 정보" in await tools["delete_brand_kit"].coroutine(state=state, name="키트")
