# 이상 감지 선제 알림(remediation advisor) — E2E 검증 가이드

> 작성 2026-07-02 (검증 성공 후 실측 기반으로 기록). 담당 🅱.
> 스펙: `docs/superpowers/specs/2026-07-02-anomaly-remediation-advisor-design.md`
> 기능 요약: 이상 감지 → 에이전트가 프로젝트 채팅 세션에 먼저 질문("어떻게 하실래요? ①②③④")
> → 벨(N5) 배지 → 사용자가 번호로 답하면 위젯(시뮬 폼/생성 폼/조치 카드)으로 진행.

---

## 0. 한눈에 보는 배달 경로 (뭘 검증하는가)

```
스캔(주기/수동) → 이상 발견(노출 0)
  → advisor.consult: 서버에서 실측 재조회·재검증 (클라이언트 데이터 불신)
  → resolver.resolve_project: 캠페인 → 프로젝트 역추적 (org fail-closed, 못 찾으면 skip)
  → chat_sink: 스팸 방지 판정표 통과 시 세션에 assistant 메시지 심기
  → 벨 🔔 (기존 N5, 미열람 세션 배지)
  → 사용자 "1번 해줘" → 서버가 consult meta를 LLM에 주입 → 해당 위젯 호출
```

검증 성공 판정 = ① 스캔 응답/요약에 `delivered: 1` ② 프로젝트에 "⚠ 캠페인 이상 알림"
세션 + 옵션 메시지 존재 ③ 재스캔 시 `skipped(bell_pending)` ④ 채팅에서 "1번" 응답 시 위젯 렌더.

## 1. 전제 조건 체크리스트

| # | 항목 | 확인 방법 | 주의 |
|---|---|---|---|
| 1 | **채널 켜기** | `.env`에 `MANAGEMENT_NOTIFY_CHANNEL=chat`(이행 노트: 구 `MANAGEMENT_CHAT_NOTIFY_ENABLED=true` → `MANAGEMENT_NOTIFY_CHANNEL=chat`) | ⚠ **활성 .env 위치**: config는 프로젝트 루트 `.env`를 **우선** 읽고, 없으면 `backend/.env`(`core/config.py:9-11`). 루트에 .env가 생기면 backend 것은 무시됨 |
| 2 | 스케줄러(선택) | 예약 실행 경로까지 보려면 `MANAGEMENT_SCHEDULER_ENABLED=true` + `MANAGEMENT_SCAN_INTERVAL_MINUTES=1` | **수동 검증엔 불필요** — notify-scan이 같은 경로를 즉시 태움 |
| 3 | 노출 0 캠페인 | 아래 §2 | live·mock 양쪽 다 기본 데이터엔 노출 0 캠페인이 **없음** → 신호 주입 필요 |
| 4 | 캠페인→프로젝트 시딩 | 아래 §3 | 없으면 `skipped(no_project_mapping)` — **버그 아님**(fail-closed) |

현재 환경 참고(2026-07-02 기준): `USE_MOCK=false` **live 모드** — reader가 실제 Meta 계정을
읽고 실캠페인 2개('잠재 고객 캠페인' `120251028376650729`, '트래픽 캠페인' `120250726096490729`,
둘 다 ended·노출>0)가 보인다. 집행은 `management_execution_mode=dry_run`이라 안전.

## 2. 감지 신호 — 노출 0 캠페인이 필요한 이유와 주입 방법

v1 감지 신호는 **impressions == 0** 하나다. 그런데,

- **live**: 실캠페인들은 노출 > 0 (집행됐던 캠페인이므로).
- **mock**: `adapters/mock.py`의 camp_1·camp_2도 합성 실측이 노출 > 0.

→ 어느 모드든 자연 발생 이상이 없어서, 검증하려면 **신호만 주입**해야 한다. 방법 2가지.

**방법 A — 하네스 스크립트(권장, 검증 완료된 방식)**: 엔드포인트와 동일한 조립
(`run_scan(scanner=…)` + `consult=partial(consult, reader=…)`)에 "특정 캠페인의 노출만
0으로 보이는 래퍼 reader"를 꽂는다. **프로덕션 코드 무변경**, 감지 신호 외 전부 실물
(resolver·판정표·DB 배달·LLM polish). 스크립트 전문은 §8.

**방법 B — mock에 노출 0 캠페인 추가**: `mock.py`에 camp_3(impressions=0)를 추가하면
HTTP 엔드포인트만으로 검증 가능. 단 mock.py는 detection(🅰)과 공유라 **사전 확인 필요**
(합의문서 §6 — mock 소유 미지정).

## 3. 시딩 — 캠페인↔프로젝트 연결 (배달 성립의 필수 전제)

resolver는 "이 캠페인이 우리 플랫폼에서 집행된 기록"(`ad_campaign_logs` → `ad_generations`
→ `projects`)으로 프로젝트를 찾는다. 검증용 캠페인은 그 기록이 없으므로 수동으로 심는다.

```sql
-- <project_id> = 알림 받을 프로젝트 id, <campaign_id> = §2에서 정한 캠페인 id
WITH gen AS (
  INSERT INTO ad_generations (id, project_id, status, input)
  VALUES (gen_random_uuid(), '<project_id>', 'completed', '{}')
  RETURNING id
)
INSERT INTO ad_campaign_logs (id, generation_id, campaign_id, status, mocked)
SELECT gen_random_uuid(), id, '<campaign_id>', 'mocked', true FROM gen;
```

⚠ **`id`를 반드시 명시** — 2026-07-02 dev 머지의 alembic baseline 재프로비전 이후
`ad_generations.id`에 DB default(gen_random_uuid())가 **없다**. 생략하면
`NotNullViolationError`. (구 DB엔 default가 있었음 — 스키마 세대에 따라 다름.)

부작용: `ad_generations` 1행이 프로젝트 생성 목록에 빈 껍데기로 보일 수 있음.
`mocked=true` 표식이 있어 §7 정리 SQL로 흔적 없이 제거 가능.

## 4. 실행 — 하네스 돌리기

```bash
cd backend
PYTHONIOENCODING=utf-8 uv run python <스크립트 경로>/seed_and_verify.py
```

기대 출력(2026-07-02 실제 검증 출력).

```
[0] project=100cfd31-… org=e33b37c6-…
[1] 시딩 완료 — ad_generations + ad_campaign_logs (mocked=true)
[2] resolver: 120250726096490729 -> ('100cfd31-…', 'e33b37c6-…')
[3] scan findings=1 summary={'delivered': 1, 'skipped': [], 'failed': []}
[4] 세션=823e74e4-… 제목=⚠ 캠페인 이상 알림
    meta.kind=remediation_consult anomaly=no_delivery
    메시지: **트래픽 캠페인**에서 이상이 발견되었습니다. … ① 시뮬레이션으로 소재 점검 …
[5] 재스캔 summary={'delivered': 0, 'skipped': [{…'reason': 'bell_pending'}], 'failed': []}
```

- `[3] delivered: 1` — 배달 성공. LLM 키가 있으면 인트로 문구가 다듬어져 나온다(옵션
  블록 ①②③④는 항상 결정론 — LLM이 못 만짐).
- `[5] bell_pending` — 스팸 방지: 사용자가 아직 안 읽었으므로 재통지 생략. **정상.**

## 5. 프론트 확인 (눈으로 보는 부분)

1. 백엔드·프론트 기동 (`uv run uvicorn api.main:app --reload --port 8000` / `pnpm dev`).
2. 로그인 → **시딩한 프로젝트 선택** — 벨은 현재 선택 프로젝트 스코프로만 폴링됨
   (`FloatingChat.tsx`). 다른 프로젝트를 보고 있으면 배지 안 뜸.
3. 채팅 벨 🔔에 "⚠ 캠페인 이상 알림" 세션 배지 확인 → 열면 상담 메시지.
4. **"1번 해줘"** 입력 → 서버가 consult meta(옵션표)를 LLM 컨텍스트로 주입 →
   `run_simulation`(①이 시뮬 점검일 때) 위젯 렌더 확인.
5. 세션을 읽은 뒤 재스캔하면 `skipped(cooldown)`(24h) — 쿨다운 경과 후 이상 지속 시
   "지난번 알려드린 건이 아직 계속되고 있어요" 후속 어조로 재통지.

수동 HTTP 트리거로 하려면 `POST /api/management/anomaly/notify-scan`(로그인 토큰 필요,
org 스코프·잠금 409·쿨다운 429). 응답에 `{scanned_findings, delivered, skipped, failed}`.

## 6. 트러블슈팅 (실제로 겪은 것들)

| 증상 | 원인 | 해결 |
|---|---|---|
| `skipped: no_project_mapping` | 시딩 누락 or 다른 campaign_id로 시딩 | §3 재확인. fail-closed **정상 동작** |
| `skipped: verified_normal` | 대상 캠페인 노출 > 0 — advisor 재검증이 "정상" 판정 | 신호 주입 대상 확인(§2). 재검증이 작동한다는 증거 |
| `skipped: bell_pending` / `cooldown` | 스팸 방지 판정표 | 정상. 새 세션으로 보려면 §7 정리 후 재실행 |
| `NotNullViolationError: id` | 새 baseline엔 id DB default 없음 | 시딩 SQL에 `gen_random_uuid()` 명시(§3) |
| `column m.meta does not exist` | ORM 속성 `meta`의 실제 컬럼명은 **`metadata`** (`core/models.py:382`) | raw SQL은 `metadata->>'kind'` 사용 |
| 스캔이 캠페인을 못 봄 | `USE_MOCK` 값과 기대 불일치 (live면 실캠페인, mock이면 camp_1·2) | `.env`의 `USE_MOCK` 확인 — **backend/.env가 활성**(루트에 .env 없을 때) |
| env를 바꿨는데 안 먹음 | `extra="ignore"` — config에 필드 선언 없는 키는 무시 | 4개 키는 이미 선언됨(`config.py`). 새 키 추가 시 필드 선언 필수 |
| 벨이 안 뜸 | 다른 프로젝트 선택 중 | 시딩한 프로젝트로 전환(§5-2) |

## 7. 정리(cleanup) — 검증 흔적 제거

```sql
-- ① 시딩 제거 (mocked 표식으로 특정)
DELETE FROM ad_generations WHERE id IN (
  SELECT generation_id FROM ad_campaign_logs
  WHERE campaign_id = '<campaign_id>' AND mocked = true
);
DELETE FROM ad_campaign_logs WHERE campaign_id = '<campaign_id>' AND mocked = true;

-- ② 알림 세션 제거 (메시지는 CASCADE)
DELETE FROM chat_sessions
WHERE title = '⚠ 캠페인 이상 알림' AND project_id = '<project_id>';
```

(①은 FK가 SET NULL이라 순서 무관하지만, generation을 먼저 지우면 log의 generation_id가
NULL로 남으니 위 순서(조회 후 삭제)를 권장.)

## 8. 하네스 스크립트 전문

`backend/`에서 실행. 멱등(재실행 시 시딩 재사용). PROJECT_ID·CAMPAIGN_ID만 바꿔 쓰면 된다.

```python
# E2E 검증 하네스 — 시딩 후 실제 sink 경로로 배달까지 확인 (프로덕션 코드 무변경)
from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime

sys.path.insert(0, r"C:\Users\804-0\click_me\backend")  # 자기 환경 경로로 조정

from sqlalchemy import text

PROJECT_ID = "<project_id>"
CAMPAIGN_ID = "<campaign_id>"  # 노출 0으로 주입할 캠페인


class ZeroImpressionReader:
    """실제 reader 위임 + 대상 캠페인 노출만 0 — 엔드포인트의 reader 주입과 동일 지점."""

    def __init__(self, inner):
        self._inner = inner

    async def list_campaigns(self, include_archived: bool = False):
        return await self._inner.list_campaigns()

    async def get_metrics(self, campaign_id: str, since):
        m = await self._inner.get_metrics(campaign_id, since)
        if campaign_id == CAMPAIGN_ID:
            return m.model_copy(update={"impressions": 0})
        return m

    def __getattr__(self, name):
        return getattr(self._inner, name)


async def main() -> None:
    from core.config import settings
    from core.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        org_id = (
            await db.execute(
                text("SELECT organization_id FROM projects WHERE id = :p"), {"p": PROJECT_ID}
            )
        ).scalar()
    print(f"[0] project={PROJECT_ID} org={org_id}")

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                text(
                    "SELECT l.id FROM ad_campaign_logs l JOIN ad_generations g "
                    "ON g.id = l.generation_id WHERE l.campaign_id = :c AND g.project_id = :p"
                ),
                {"c": CAMPAIGN_ID, "p": PROJECT_ID},
            )
        ).scalar()
        if existing:
            print(f"[1] 시딩 이미 존재 — 재사용")
        else:
            await db.execute(
                text(
                    "WITH gen AS (INSERT INTO ad_generations (id, project_id, status, input) "
                    "VALUES (gen_random_uuid(), :p, 'completed', '{}') RETURNING id) "
                    "INSERT INTO ad_campaign_logs (id, generation_id, campaign_id, status, mocked) "
                    "SELECT gen_random_uuid(), id, :c, 'mocked', true FROM gen"
                ),
                {"p": PROJECT_ID, "c": CAMPAIGN_ID},
            )
            await db.commit()
            print("[1] 시딩 완료")

    from domain.management.remediation.resolver import resolve_project

    resolved = await resolve_project(CAMPAIGN_ID)
    print(f"[2] resolver: {CAMPAIGN_ID} -> {resolved}")
    assert resolved and resolved[0] == PROJECT_ID, "resolver 역추적 실패"

    from functools import partial

    from domain.management.notifications import LogNotificationSink
    from domain.management.remediation.advisor import consult
    from domain.management.remediation.chat_sink import ChatNotificationSink
    from domain.management.scheduler import run_scan
    from domain.management.wiring import build_reader

    reader = ZeroImpressionReader(build_reader(settings))

    async def org_scanner(_settings):
        findings = []
        now = datetime.now(UTC)
        for c in await reader.list_campaigns():
            m = await reader.get_metrics(c.campaign_id, now)
            if m.impressions == 0:
                findings.append(
                    {
                        "tenant_id": str(org_id),
                        "title": f"게재 점검 — {c.name}",
                        "body": "활성 캠페인인데 노출이 0입니다.",
                        "meta": {"campaign_id": c.campaign_id},
                    }
                )
        return findings

    sink = ChatNotificationSink(
        settings, fallback=LogNotificationSink(), consult=partial(consult, reader=reader)
    )
    count = await run_scan(settings, sink, scanner=org_scanner)
    print(f"[3] scan findings={count} summary={sink.summary()}")

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                text(
                    "SELECT s.id, s.title, m.content, m.metadata->>'kind', "
                    "m.metadata->>'anomaly_type' "
                    "FROM chat_sessions s JOIN chat_messages m ON m.session_id = s.id "
                    "WHERE s.project_id = :p AND s.title LIKE '%이상 알림%' "
                    "ORDER BY m.created_at DESC LIMIT 1"
                ),
                {"p": PROJECT_ID},
            )
        ).first()
    print(f"[4] {'세션=' + str(row[0]) if row else '❌ 메시지 없음'}")
    if row:
        print(f"    meta.kind={row[3]} anomaly={row[4]}\n    메시지: {row[2][:150]}...")

    sink2 = ChatNotificationSink(
        settings, fallback=LogNotificationSink(), consult=partial(consult, reader=reader)
    )
    await run_scan(settings, sink2, scanner=org_scanner)
    print(f"[5] 재스캔 summary={sink2.summary()}  (skipped=bell_pending 기대)")


if __name__ == "__main__":
    asyncio.run(main())
```

## 9. 2026-07-02 검증 기록

- 환경: live(USE_MOCK=false, dry_run) · 대상: 트래픽 캠페인(`120250726096490729`, 노출 주입)
  · 프로젝트: 매니지먼트 캠페인(`100cfd31-…`).
- 결과: [1]~[5] 전부 기대대로 — delivered 1건, LLM polish 적용된 인트로 + 결정론 옵션 4개,
  재스캔 bell_pending. 시딩·알림 세션은 프론트 확인 후 §7로 정리 예정.
- 프론트 확인(벨→"1번 해줘"→위젯)은 사용자 화면에서 수행.
