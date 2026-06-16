"""Meta Marketing API 호출 누적기 — 등급 상향 자격(15일 500콜)용 워밍업.

토큰·계정은 .env(core.config.settings)에서만 읽고, 호출은 MetaClient 공통층을
재사용한다(토큰/시크릿 자동 마스킹·버전·act_ 접두사 그대로 사용).

실행:  cd backend && uv run python scripts/meta_warmup.py [목표콜수] [--delay 초]
.env:  META_ACCESS_TOKEN(시스템유저 토큰 권장) · META_AD_ACCOUNT_ID(act_ 포함)

주의: rate limit 존중 — 한 번에 폭주 금지. 15일 창이니 하루 40~60개씩 나눠 권장.
계정ID 있으면 insights('진짜 사용'에 가까움), 없으면 me/adaccounts로 누적.
"""

from __future__ import annotations

# ruff: noqa: E402 — sys.path 부트스트랩 후 import (스크립트 단독 실행 지원)
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/를 모듈 경로에 추가

from core.config import settings
from domain.management.adapters.meta.client import MetaApiError, MetaClient

# rate limit 계열 신호 (Graph error code 4/17/613, HTTP 429)
_RATE_SIGNALS = ('"code":4', '"code":17', '"code":613', " 429:", "429")


def _build_call(acct: str | None) -> tuple[str, dict[str, str]]:
    if acct:
        return f"{acct}/insights", {
            "fields": "impressions,spend,cpm,ctr",
            "date_preset": "last_7d",
        }
    return "me/adaccounts", {"fields": "account_id,name,account_status"}


async def run(target: int, delay: float) -> None:
    client = MetaClient(settings)
    path, params = _build_call(settings.meta_ad_account_id)
    print(f"엔드포인트 {path} · 목표 성공 {target}콜 · 간격 {delay}s", flush=True)

    ok = fail = attempts = 0
    max_attempts = target * 3  # 전량 실패 시 무한루프 방지
    while ok < target and attempts < max_attempts:
        attempts += 1
        try:
            await client.get(path, params)
            ok += 1
            if ok % 10 == 0:
                print(f"  진행 성공 {ok}/{target} (실패 {fail})", flush=True)
        except MetaApiError as exc:
            fail += 1
            msg = str(exc)
            print(f"  [{attempts}] 실패: {msg[:160]}", flush=True)
            if any(sig in msg for sig in _RATE_SIGNALS):
                print("  rate limit 감지 — 60초 대기", flush=True)
                await asyncio.sleep(60)
                continue
        await asyncio.sleep(delay)

    print(f"\n완료: 성공 {ok} / 실패 {fail} / 시도 {attempts} · 엔드포인트 {path}", flush=True)
    print("→ App Dashboard > Marketing API 에서 누적 콜 수 확인 (목표 15일 500)", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Meta 500콜 워밍업")
    parser.add_argument("target", nargs="?", type=int, default=50, help="목표 성공 콜 수")
    parser.add_argument("--delay", type=float, default=3.0, help="호출 간격(초)")
    args = parser.parse_args()
    asyncio.run(run(args.target, args.delay))


if __name__ == "__main__":
    main()
