# 제너레이터 실행 확정 지점의 실행 히스토리(롱텀) 적재 골든 — 파이프라인 완료·후보확정·게시 검증
"""_run_pipeline·select_candidate·publish_candidate에서 record_execution이 호출되는지 고정한다.

- record_execution을 monkeypatch로 캡처(DB 없이 검증) → feature_type·action·summary·stage 계약 고정.
- graph·영속·상태갱신·세션은 모킹해 적재 로직만 결정론으로 검증.
- 실패(파이프라인 예외·게시 실패) 시 적재하지 않음도 고정 — 롱텀은 "성공한 수행만".
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from domain.generator.contracts.enums import GenerationMode
from domain.generator.contracts.schemas import GenerationCreateRequest
from domain.generator.service import generator_service

_PROJECT = "11111111-1111-1111-1111-111111111111"


def _request(mode: GenerationMode = GenerationMode.CREATE) -> GenerationCreateRequest:
    return GenerationCreateRequest(
        mode=mode,
        product_name="수분크림",
        product_description="24시간 보습",
        target_audience="20대 여성",
        campaign_objective="conversion",
        project_id=_PROJECT,
        # improve 모드 필수 필드(create에선 무시됨)
        simulation_summary="클릭 의향 낮음 — CTA 개선 필요"
        if mode == GenerationMode.IMPROVE
        else None,
    )


@pytest.fixture
def patched(monkeypatch):
    """graph·영속·상태갱신 모킹 + record_execution 호출 캡처를 반환."""
    captured: list[dict] = []

    async def _ainvoke(state, config=None):  # noqa: ANN001
        return {"candidates": [{"idx": 0}, {"idx": 1}]}

    async def _noop(*a, **k):  # noqa: ANN002, ANN003
        return None

    async def _record(project_id, feature_type, action, summary, payload=None, user_id=None):  # noqa: ANN001
        captured.append(
            {
                "project_id": project_id,
                "feature_type": feature_type,
                "action": action,
                "summary": summary,
                "payload": payload,
                "user_id": user_id,
            }
        )

    monkeypatch.setattr(generator_service.generation_graph, "ainvoke", _ainvoke)
    monkeypatch.setattr(generator_service, "_persist_results", _noop)
    monkeypatch.setattr(generator_service, "_update_status", _noop)
    monkeypatch.setattr(generator_service, "record_execution", _record)
    return captured


async def test_pipeline_completion_records_execution(patched):
    gid = str(uuid.uuid4())
    user = uuid.uuid4()
    generator_service._tasks[gid] = {"status": "pending", "events": []}

    await generator_service._run_pipeline(gid, _request(), created_by=user)

    assert len(patched) == 1
    row = patched[0]
    assert row["project_id"] == _PROJECT
    assert row["feature_type"] == "generation"
    assert row["action"] == "run_generation"
    # summary는 BM25(simple 토큰) 서치 대상 — 한글 라벨·상품명 포함
    assert "생성 완료" in row["summary"]
    assert "수분크림" in row["summary"]
    assert "시안 2개" in row["summary"]
    assert row["payload"]["stage"] == "completed"
    assert row["payload"]["generation_id"] == gid
    assert row["user_id"] == str(user)


async def test_improve_mode_records_run_improvement(patched):
    gid = str(uuid.uuid4())
    generator_service._tasks[gid] = {"status": "pending", "events": []}

    await generator_service._run_pipeline(gid, _request(GenerationMode.IMPROVE))

    assert len(patched) == 1
    assert patched[0]["action"] == "run_improvement"
    assert patched[0]["payload"]["mode"] == "improve"
    assert patched[0]["user_id"] is None


async def test_pipeline_failure_does_not_record(patched, monkeypatch):
    async def _boom(state, config=None):  # noqa: ANN001
        raise RuntimeError("파이프라인 실패")

    monkeypatch.setattr(generator_service.generation_graph, "ainvoke", _boom)
    gid = str(uuid.uuid4())
    generator_service._tasks[gid] = {"status": "pending", "events": []}

    await generator_service._run_pipeline(gid, _request())

    assert patched == []
    assert generator_service._tasks[gid]["status"] == "failed"


# --- select_candidate · publish_candidate 적재 계약 -------------------------


class _FakeSession:
    """AsyncSessionLocal 대체 — (모델명, pk) 키로 미리 심은 객체를 돌려주는 가짜 세션."""

    def __init__(self, objects: dict) -> None:
        self._objects = objects
        self.added: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):  # noqa: ANN002
        return False

    async def get(self, model, pk):  # noqa: ANN001
        return self._objects.get((model.__name__, pk))

    async def commit(self) -> None:
        return None

    def add(self, obj) -> None:  # noqa: ANN001
        self.added.append(obj)


@pytest.fixture
def gen_ids():
    return uuid.uuid4(), uuid.uuid4()  # (gid, cid)


def _fake_db(monkeypatch, gid: uuid.UUID, cid: uuid.UUID, *, selected: bool) -> None:
    generation = SimpleNamespace(
        project_id=uuid.UUID(_PROJECT),
        input={"product_name": "수분크림"},
        selected_candidate_id=cid if selected else None,
    )
    candidate = SimpleNamespace(
        generation_id=gid,
        idx=1,
        copy={"headline": "촉촉함의 끝"},
        s3_key="generations/x/candidate_1.png",
    )
    objects = {("AdGeneration", gid): generation, ("AdGenerationCandidate", cid): candidate}
    monkeypatch.setattr(generator_service, "AsyncSessionLocal", lambda: _FakeSession(objects))


def _patch_publish_io(monkeypatch, *, success: bool, mocked: bool) -> None:
    """S3 입출력·퍼블리셔를 모킹 — 게시 결과(성공/모의/실패)만 제어."""

    async def _bytes(*a, **k):  # noqa: ANN002, ANN003
        return b"png"

    async def _none(*a, **k):  # noqa: ANN002, ANN003
        return None

    async def _url(*a, **k):  # noqa: ANN002, ANN003
        return "https://s3/presigned.jpg"

    outcome = SimpleNamespace(
        success=success,
        mocked=mocked,
        media_id="media-1" if success else None,
        container_id=None,
        raw={},
        error=None if success else "IG 오류",
    )

    class _Publisher:
        async def publish_image(self, image_url, caption):  # noqa: ANN001
            return outcome

    monkeypatch.setattr(generator_service, "download_bytes", _bytes)
    monkeypatch.setattr(generator_service, "upload_bytes", _none)
    monkeypatch.setattr(generator_service, "presign_get", _url)
    monkeypatch.setattr(generator_service, "png_to_jpeg", lambda b, quality=90: b"jpeg")
    monkeypatch.setattr(generator_service, "build_publisher", lambda: _Publisher())


async def test_select_candidate_records_execution(patched, monkeypatch, gen_ids):
    gid, cid = gen_ids
    _fake_db(monkeypatch, gid, cid, selected=False)
    user = str(uuid.uuid4())

    ok = await generator_service.select_candidate(str(gid), str(cid), created_by=user)

    assert ok is True
    assert len(patched) == 1
    row = patched[0]
    assert row["project_id"] == _PROJECT
    assert row["feature_type"] == "generation"
    assert row["action"] == "select_candidate"
    assert "후보 확정" in row["summary"]
    assert "수분크림" in row["summary"]
    assert "후보 2번" in row["summary"]  # idx=1 → 사용자 표기 2번
    assert row["payload"]["stage"] == "completed"
    assert row["payload"]["candidate_id"] == str(cid)
    assert row["user_id"] == user


async def test_publish_published_records_execution(patched, monkeypatch, gen_ids):
    gid, cid = gen_ids
    _fake_db(monkeypatch, gid, cid, selected=True)
    _patch_publish_io(monkeypatch, success=True, mocked=False)

    result = await generator_service.publish_candidate(str(gid), str(cid), "여름 보습 필수템")

    assert result["status"] == "published"
    assert len(patched) == 1
    row = patched[0]
    assert row["action"] == "publish_ad"
    assert "인스타그램 게시 완료" in row["summary"]
    assert "여름 보습 필수템" in row["summary"]
    assert row["payload"]["status"] == "published"
    assert row["payload"]["media_id"] == "media-1"


async def test_publish_mocked_records_with_mock_label(patched, monkeypatch, gen_ids):
    gid, cid = gen_ids
    _fake_db(monkeypatch, gid, cid, selected=True)
    _patch_publish_io(monkeypatch, success=True, mocked=True)

    result = await generator_service.publish_candidate(str(gid), str(cid), "캡션")

    assert result["status"] == "mocked"
    assert len(patched) == 1
    assert "게시 완료(모의)" in patched[0]["summary"]
    assert patched[0]["payload"]["status"] == "mocked"


async def test_publish_failed_does_not_record(patched, monkeypatch, gen_ids):
    gid, cid = gen_ids
    _fake_db(monkeypatch, gid, cid, selected=True)
    _patch_publish_io(monkeypatch, success=False, mocked=False)

    result = await generator_service.publish_candidate(str(gid), str(cid), "캡션")

    assert result["status"] == "failed"
    assert patched == []  # 롱텀은 성공한 수행만 — 실패 정본은 AdPublishLog
