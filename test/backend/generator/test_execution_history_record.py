# 제너레이터 파이프라인 완료 시 실행 히스토리(롱텀) 적재 골든 — UI·채팅·루프 공통 수렴 지점 검증
"""_run_pipeline 성공 분기에서 record_execution이 호출되는지 고정한다.

- record_execution을 monkeypatch로 캡처(DB 없이 검증) → feature_type·action·summary·stage 계약 고정.
- graph·영속·상태갱신은 모킹해 적재 로직만 결정론으로 검증.
- 실패(파이프라인 예외) 시 적재하지 않음도 고정 — 롱텀은 "성공한 수행만".
"""

from __future__ import annotations

import uuid

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
