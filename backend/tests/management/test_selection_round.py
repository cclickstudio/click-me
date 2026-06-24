# 🅱 HITL 선택 라운드 영속 — v1 InMemory 최소 무결성 테스트
from datetime import UTC, datetime, timedelta

import pytest

from domain.management.agents.selection import (
    InMemorySelectionRoundStore,
    SelectionRound,
)


def _round(token="tok_1", tenant="org_1", ttl_min=10):
    now = datetime.now(UTC)
    return SelectionRound(
        selection_token=token,
        tenant_id=tenant,
        candidate_ids=("c0", "c1"),
        expires_at=now + timedelta(minutes=ttl_min),
        created_at=now,
    )


@pytest.mark.asyncio
async def test_save_then_claim_membership_and_tenant_ok():
    store = InMemorySelectionRoundStore()
    await store.save(_round())
    rnd = await store.claim("tok_1", tenant_id="org_1", selected_id="c0")
    assert rnd.selection_token == "tok_1"


@pytest.mark.asyncio
async def test_claim_rejects_non_member():
    store = InMemorySelectionRoundStore()
    await store.save(_round())
    with pytest.raises(ValueError, match="membership"):
        await store.claim("tok_1", tenant_id="org_1", selected_id="cX")


@pytest.mark.asyncio
async def test_claim_rejects_wrong_tenant():
    store = InMemorySelectionRoundStore()
    await store.save(_round())
    with pytest.raises(ValueError, match="tenant"):
        await store.claim("tok_1", tenant_id="org_2", selected_id="c0")


@pytest.mark.asyncio
async def test_claim_rejects_expired():
    store = InMemorySelectionRoundStore()
    await store.save(_round(ttl_min=-1))
    with pytest.raises(ValueError, match="expired"):
        await store.claim("tok_1", tenant_id="org_1", selected_id="c0")


@pytest.mark.asyncio
async def test_single_shot_second_claim_rejected():
    store = InMemorySelectionRoundStore()
    await store.save(_round())
    await store.claim("tok_1", tenant_id="org_1", selected_id="c0")
    with pytest.raises(ValueError, match="duplicate"):
        await store.claim("tok_1", tenant_id="org_1", selected_id="c1")
