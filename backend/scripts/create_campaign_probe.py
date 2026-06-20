# 인앱 캠페인 생성 플로우 실연동 검증 — create-proposal → approve → execute 3단 호출.
"""Task2 검증 스크립트 — 버튼 흐름과 무관하게 생성 플로우를 직접 친다.

전제: 백엔드가 USE_MOCK=false + MANAGEMENT_EXECUTION_MODE=validate_only(또는 live)로 떠 있을 것.
- validate_only → Meta가 요청을 검증만(생성 0·과금 0). 토큰·요청 형태 OK인지 확인.
- live        → 실제 캠페인이 PAUSED로 생성됨(게재 X라 과금 0).
실행:  cd backend && uv run python scripts/create_campaign_probe.py
"""

import asyncio
import json

import httpx

BASE = "http://localhost:8000/api/management"


async def main() -> None:
    async with httpx.AsyncClient(timeout=30) as c:
        # 1) 제안 — 리드 캠페인, 소액
        r = await c.post(
            f"{BASE}/campaigns/create-proposal",
            json={
                "name": "리드_신규문의_즉석양식_2606_t1",
                "objective": "leads",
                "daily_budget_krw": 2000,
                "run_days": 3,
            },
        )
        r.raise_for_status()
        proposal = r.json()["proposal"]
        print("1) 제안 생성 OK :", proposal["proposal_id"], "/ tier", proposal["action_tier"])

        # 2) 승인 — execution_mode는 서버가 settings(validate_only/live)로 결정
        r = await c.post(f"{BASE}/approve", json={"proposal": proposal, "approved": True})
        r.raise_for_status()
        body = r.json()
        if body.get("status") != "approved":
            print("승인 거부/이슈:", json.dumps(body, ensure_ascii=False))
            return
        action = body["approved_action"]
        print("2) 승인 OK      :", action["approval_id"], "/ mode", action["execution_mode"])

        # 3) 실행 — validate_only면 검증만, live면 실제 PAUSED 생성
        r = await c.post(
            f"{BASE}/execute",
            json={"approved_action": action, "proposal": proposal},
        )
        r.raise_for_status()
        result = r.json()["result"]
        print("3) 실행 결과    :")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print()
        if result["status"] == "success":
            print("✅ 성공 — validate_only면 요청 검증 통과, live면 캠페인 생성됨.")
        else:
            print("⚠ 실패 — failure_reason 확인. 토큰 스코프(ads_management)·요청 형태 점검.")


if __name__ == "__main__":
    asyncio.run(main())
