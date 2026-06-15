"""Meta Marketing API 호출 누적기 — 등급 상향 자격(15일 500콜)용 워밍업.

토큰은 절대 하드코딩하지 않는다 — .env(META_ACCESS_TOKEN)에서만 읽는다.
참고 자산: App ID 1519959093258659 / Business ID 2072694383286835 (이 루프엔 불필요).

실행:  cd backend && uv run python scripts/meta_warmup.py [콜수]
.env:  META_ACCESS_TOKEN(장기/시스템유저 토큰 권장) · META_AD_ACCOUNT_ID(선택, act_ 제외)

주의: rate limit 존중 위해 페이스 조절(DELAY). 한 번에 500 폭주 금지 —
15일 창이니 하루 40~60개씩 나눠 돌려라. insights(계정ID 있을 때)가 me/adaccounts보다
'진짜 사용'에 가깝다.
"""

import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("META_ACCESS_TOKEN")
ACCT = os.getenv("META_AD_ACCOUNT_ID")  # act_ 제외 숫자
VER = os.getenv("META_API_VERSION", "v23.0")
DELAY_SEC = 3.0  # 초당 1회 미만 — rate limit 안전

if not TOKEN:
    sys.exit("META_ACCESS_TOKEN 미설정 — backend/.env에 재발급 토큰을 넣어라(노출 토큰 폐기).")

N = int(sys.argv[1]) if len(sys.argv) > 1 else 50

# 계정ID 있으면 insights(실사용에 가까움), 없으면 me/adaccounts로 누적
if ACCT:
    path = f"act_{ACCT}/insights"
    params = {"fields": "impressions,spend,cpm,ctr", "date_preset": "last_7d"}
else:
    path = "me/adaccounts"
    params = {"fields": "account_id,name,account_status"}


def main() -> None:
    url = f"https://graph.facebook.com/{VER}/{path}"
    ok = fail = 0
    with httpx.Client(timeout=30) as client:
        for i in range(1, N + 1):
            resp = client.get(url, params={**params, "access_token": TOKEN})
            if resp.status_code == 200:
                ok += 1
            else:
                fail += 1
                body = resp.text[:160]
                print(f"  [{i}] {resp.status_code} {body}")
                # rate limit 계열(코드 4/17/613, HTTP 429) → 60초 백오프
                rate_codes = ('"code":4', '"code":17', '"code":613')
                if resp.status_code == 429 or any(c in body for c in rate_codes):
                    print("  rate limit 감지 — 60초 대기")
                    time.sleep(60)
            if i % 10 == 0:
                print(f"  진행 {i}/{N}  (성공 {ok} / 실패 {fail})")
            time.sleep(DELAY_SEC)
    print(f"\n완료: 성공 {ok} / 실패 {fail}  · 엔드포인트 {path}")
    print("→ App Dashboard > Marketing API에서 누적 콜 수 확인 (목표 15일 500)")


if __name__ == "__main__":
    main()
