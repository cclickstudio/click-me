# 세션 넘는 장기기억 — remember/recall + 네임스페이스 격리 검증
"""ManagementMemory가 (tenant, user) 네임스페이스로 cross-session 기억을 저장·회수하는지 본다.

cross-session = 별도 호출(다른 세션)에서 같은 네임스페이스로 회수됨. 다른 user/tenant는 격리.
"""

import pytest

from domain.management.assistant.memory_store import ManagementMemory


@pytest.mark.asyncio
async def test_remember_recall_cross_session():
    mem = ManagementMemory()
    await mem.remember("t1", "u1", "k1", {"note": "선호: 트래픽 목표"})
    await mem.remember("t1", "u1", "k2", {"note": "결정: camp_1 일시중지"})
    got = await mem.recall("t1", "u1", limit=5)
    notes = {g["note"] for g in got}
    assert "선호: 트래픽 목표" in notes
    assert len(got) == 2


@pytest.mark.asyncio
async def test_namespace_isolation_by_user_and_tenant():
    mem = ManagementMemory()
    await mem.remember("t1", "u1", "k", {"note": "A"})
    assert await mem.recall("t1", "u2") == []  # 다른 user
    assert await mem.recall("t2", "u1") == []  # 다른 tenant
