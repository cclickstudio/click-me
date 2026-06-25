# 어시스턴트 골든셋을 management_kb_eval_cases에 시드(평가셋 DB화 — 회귀·분석 기반).
"""assistant_eval.GOLDEN(질문→기대 도구)을 DB 평가셋으로 적재한다(멱등: fixture_version 기준 교체).

실행: cd backend && uv run python -m domain.management.evals.seed_eval_cases
"""

from __future__ import annotations

import asyncio

from sqlalchemy import delete

from core.db import AsyncSessionLocal
from core.models import ManagementKbEvalCase
from domain.management.evals.assistant_eval import GOLDEN

FIXTURE = "assistant-golden-v1"


async def seed() -> int:
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(ManagementKbEvalCase).where(ManagementKbEvalCase.fixture_version == FIXTURE)
        )
        for question, campaign_id, expected_tools, _desc in GOLDEN:
            db.add(
                ManagementKbEvalCase(
                    question=question,
                    expected_tools=sorted(expected_tools),
                    expected_campaign_id=campaign_id,
                    fixture_version=FIXTURE,
                )
            )
        await db.commit()
    print(f"평가셋 시드 완료: {len(GOLDEN)} cases ({FIXTURE})")
    return len(GOLDEN)


if __name__ == "__main__":
    asyncio.run(seed())
