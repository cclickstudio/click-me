# 발표 대비 리밸런스 데모 패키지 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **⚠️ 이 계획은 코드 태스크(Task 1~2)와 운영자(사용자) 태스크(Task 3~5)가 섞여 있다.** Task 3~5는 실돈 Meta 계정을 다루므로 **에이전트가 대신 실행하지 않는다** — 확인 프로브(읽기 전용)만 에이전트가 돌리고, 실행 액션은 사용자가 한다.

**Goal:** 발표(2026-07-14)에서 "워커 알림 → CTA → 챗 → 리밸런스 카드 → 실집행"이 실계정으로 성립하게 한다 — 알림 CTA 코드 1건 + 설정 전환 + 캠페인 셋업·리허설·라이브 가드 런북.

**Architecture:** 스펙 `docs/superpowers/specs/2026-07-11-rebalance-demo-package-design.md` 기준. 코드 변경은 anomaly 페이지 workerRuns 카드의 CTA(기존 `clio:draft` sessionStorage 패턴 재사용, 챗 페이지 무변경)뿐. 나머지는 `.env` 전환과 실계정 캠페인 구성·검증 절차.

**Tech Stack:** Next.js/TS (pnpm), backend 확인 프로브는 uv 단발 실행(읽기 전용).

---

### Task 1: 알림 CTA — 사용자 배너 + workerRuns 카드 (코드)

**Files:**
- Modify: `frontend/src/app/(app)/manage/anomaly/page.tsx` — 컴포넌트 상단(헬퍼·파생값), `:274` 근처(사용자 배너), `:290-305`(workerRuns 카드 `<li>` 내부)

주의 — 페이지 기본 모드는 `user`(46줄)이고 workerRuns 카드는 `mode === 'arch'` 전용(275줄, "내부 운영 정보라 arch에서만" 설계 의도). 데모 스토리(워커 감지→알림→적용)는 사용자 화면에서 보여야 하므로, **내부 점검 전체가 아닌 `apply_rebalance` 제안만 사용자 모드 배너로** 노출한다. arch 카드에도 같은 CTA를 단다.

- [ ] **Step 1: 헬퍼·파생값 추가** — 컴포넌트 본문(예: `workerRuns` state 선언 아래)에 추가. `'apply_rebalance'` 문자열은 백엔드 계약(scheduler.py) — 다른 값 추가 금지.

```tsx
  // 리밸런스 제안 알림 — 사용자 화면 CTA 대상(내부 점검 전체는 arch 카드에만).
  const rebalanceRuns = workerRuns.filter((r) => r.suggested_action === 'apply_rebalance');
  // 대시보드 CLIO 런처와 동일한 clio:draft 패턴(1회 소비) — 챗 페이지 무변경.
  const draftRebalanceChat = () => {
    try {
      sessionStorage.setItem('clio:draft', '리밸런스 적용해줘');
    } catch {
      /* sessionStorage 불가 환경 — 초안 없이 /chat 진입 */
    }
  };
```

- [ ] **Step 2: 사용자 모드 배너 추가** — `{/* 서버 워커 자동 점검 결과 — ... */}` 주석의 `{mode === 'arch' && (` 블록(274줄) **바로 위**에 추가.

```tsx
        {/* 리밸런스 제안 알림 — 사용자 화면에도 노출(적용 진입 CTA). 내부 점검 전체는 arch 카드. */}
        {mode === 'user' && rebalanceRuns.length > 0 && (
          <div className="mb-4 rounded-xl border border-line px-4 py-3">
            <p className="text-sm font-semibold text-ink">예산 리밸런싱 제안이 도착했어요</p>
            <p className="mt-0.5 text-[12px] text-ink-tertiary">{rebalanceRuns[0].body}</p>
            <Link
              href="/chat"
              onClick={draftRebalanceChat}
              className="mt-1 inline-block text-[12px] font-semibold text-primary hover:underline"
            >
              챗에서 리밸런스 적용하기 →
            </Link>
          </div>
        )}
```

- [ ] **Step 3: arch 카드 CTA 추가** — workerRuns 매핑의 `{r.body && <p ...>{r.body}</p>}` 바로 아래. 기존 `suggested_action === 'REPLACE_CREATIVE'` CTA(254-260줄)와 같은 링크 스타일.

```tsx
                  {r.body && <p className="text-[12px] text-ink-tertiary">{r.body}</p>}
                  {r.suggested_action === 'apply_rebalance' && (
                    <Link
                      href="/chat"
                      onClick={draftRebalanceChat}
                      className="mt-1 inline-block text-[12px] font-semibold text-primary hover:underline"
                    >
                      챗에서 리밸런스 적용하기 →
                    </Link>
                  )}
```

- [ ] **Step 4: 빌드로 검증**

Run: `cd frontend && pnpm build`
Expected: 타입 에러 0, 빌드 성공. (`AutomationRunItem.suggested_action`은 `lib/api.ts`에 이미 선언돼 있음 — 타입 추가 불필요.)

- [ ] **Step 5: 커밋**

```bash
git add "frontend/src/app/(app)/manage/anomaly/page.tsx"
git commit -m "add: 리밸런스 워커 알림 CTA — 사용자 배너 + arch 카드, clio:draft 재사용"
```

---

### Task 2: 설정 전환【사용자 승인 하】 + 확인 프로브【에이전트, 읽기 전용】

**Files:**
- Modify: `backend/.env:172`(READER_MOCK), `:92`(EXECUTION_MODE) — **미추적 로컬 파일, 커밋 없음**

Step 1은 로컬 설정 **변경**(실 Meta reader로 동작 전환)이라 읽기 전용이 아니다 — 사용자 승인 하에 수행한다. 에이전트가 자율 실행 가능한 건 Step 2부터(프로브는 Meta GET만).

- [ ] **Step 1【설정 변경 — 사용자 승인 필요】: .env 두 줄 변경** — 아래 두 줄만. 다른 줄(토큰·계정·USE_MOCK)은 절대 건드리지 않는다.

```bash
# 변경 전 → 후
MANAGEMENT_READER_MOCK=true   → MANAGEMENT_READER_MOCK=false
MANAGEMENT_EXECUTION_MODE=live → MANAGEMENT_EXECUTION_MODE=validate_only
```

- [ ] **Step 2【에이전트 가능】: 전환 검증 프로브 (읽기 전용)**

Run:
```bash
cd backend && uv run python -c "
import sys; sys.path.insert(0, '.')
from core.config import settings
from domain.management.wiring import build_reader, resolve_execution_mode
print('reader:', type(build_reader(settings)).__name__)
print('mode:', resolve_execution_mode(settings))
"
```
Expected: `reader: MetaAdsReader` (Mock 아님) / `mode: ExecutionMode.VALIDATE_ONLY`. 다르면 .env 오탈자 확인.

- [ ] **Step 3【에이전트 가능】: 실계정 현황 프로브 (읽기 전용 — Meta GET만)** — 캠페인별 last_7d 실측(clicks/spend/cpc)까지 출력해, 제안 미발동 시 "실측 부족 vs CPC 격차 1.2배 미달"을 즉시 분기할 수 있게 한다.

Run:
```bash
cd backend && uv run python -c "
import asyncio, json, sys; sys.path.insert(0, '.')
from datetime import UTC, datetime
from core.config import settings
from domain.management.wiring import build_reader
from domain.management import insights

async def main():
    reader = build_reader(settings)
    now = datetime.now(UTC)
    camps = await reader.list_campaigns()
    for c in camps:
        line = f'{c.campaign_id} | state: {c.state} | type: {getattr(c, \"budget_type\", \"?\")} | daily: {getattr(c, \"daily_budget_krw\", 0)}'
        try:
            m = await reader.get_metrics(c.campaign_id, now, date_preset='last_7d')
            line += f' | 7d clicks: {getattr(m, \"clicks\", 0)} | spend: {getattr(m, \"spend_krw\", 0)} | cpc: {getattr(m, \"cpc_krw\", 0)}'
        except Exception as exc:
            line += f' | metrics 실패: {exc}'
        print(line)
    print(json.dumps(await insights.rebalance_proposal(reader), ensure_ascii=False, default=str))

asyncio.run(main())
"
```
Expected (Task 3 전): 활성 daily 캠페인 0개 → `"proposal": null` + "진행 중(일예산형) 캠페인이 있으면 제안해요" — 이게 현 상태의 정답. Task 3 이후 다시 돌려 활성 daily 2개·실측·제안 발동을 확인한다.
판독 가이드 — 두 캠페인 모두 `7d clicks > 0`인데 제안이 null이고 note가 "CPC 격차" 언급이면 **격차 미달**(플랜 B-1: 타게팅·입찰 조정), clicks가 0이면 **실측 부족**(대기).

---

### Task 3: 캠페인 셋업 (D-3) — 【사용자 액션】

**에이전트는 실행하지 않는다. 사용자가 수행 후 Task 2 Step 3 프로브로 확인만 대행한다.**

- [ ] **Step 1【사용자】**: 플랫폼 create_campaign 플로우(챗 "새 캠페인 만들기" 또는 시뮬 결과 집행 카드)로 소액 daily 캠페인 A 생성 — 일예산 ₩2,000~3,000, 타게팅 **광범위**(저CPC 유도).
- [ ] **Step 2【사용자】**: 같은 방식으로 캠페인 B 생성 — 일예산 ₩2,000~3,000, 타게팅 **좁게**(고CPC 유도). 두 캠페인 일예산 합계 ≤ ₩6,000 확인.
- [ ] **Step 3【사용자】**: 두 캠페인 게재 시작(activate — 실과금 시작 확인 체크). 기존 lifetime 활성·paused 캠페인은 무변경.
- [ ] **Step 4【에이전트 가능】**: Task 2 Step 3 프로브 재실행 → 활성 daily 2개 확인 (제안은 실측 누적 전이라 아직 null이어도 정상).

---

### Task 4: 실측·발동 확인 + validate 리허설 (D-2 ~ D-1) — 【사용자 주도】

- [ ] **Step 1【에이전트 가능】**: Task 2 Step 3 프로브 → 두 캠페인 클릭·지출 > 0, `"kind": "transfer"` 제안 발동 확인. 미발동이면 사유 분기 — 실측 부족(하루 더 대기) vs CPC 격차 1.2배 미달(스펙 §1-5 플랜 B-1: 타게팅·입찰 조정).
- [ ] **Step 2【사용자】**: validate_only 리허설 — `/manage/budget` 적용 버튼 또는 챗 "리밸런스 적용해줘" 카드로 rebalance-commit 1회 실행. 기대: 응답 SUCCESS + Meta 광고관리자에서 **예산 무변경** 교차 확인. 이 기록이 라이브 전환의 전제.
- [ ] **Step 3【사용자】**: CTA 리허설 — `/manage/anomaly` **기본(사용자) 화면의 리밸런스 제안 배너**에서 "챗에서 리밸런스 적용하기 →" 클릭 → `/chat` → 프로젝트 선택 → 새 채팅 → 입력창에 "리밸런스 적용해줘" 프리필 확인. arch(내부 동작) 탭의 workerRuns 카드 CTA도 동일 동작인지 확인. (워커 알림이 아직 없으면 서버를 켜두고 리밸런스 잡 주기(`MANAGEMENT_REBALANCE_INTERVAL_MINUTES`) 경과 후 재확인 — 리허설 동안만 짧게 줄여도 됨, 제안 전용 잡이라 안전.)
- **플랜 B 주의**: 워커는 **transfer 제안일 때만** `suggested_action=apply_rebalance`를 남긴다(adjust는 None). 플랜 B-2(kind=adjust 폴백)로 가면 알림 배너·CTA가 없으므로 **챗에서 "리밸런스 적용해줘"를 직접 입력**하는 흐름으로 데모를 시작한다 — 스토리 서술도 그에 맞게 조정.

---

### Task 5: D-day 라이브 가드 — 【전부 사용자 액션, 에이전트 실행 금지】

스펙 §1-4를 체크리스트로 그대로 수행한다.

- [ ] 전제 3종 확인: validate 리허설 성공 기록 / 당일 아침 제안 발동 재확인 / 일예산 합계 ≤ ₩6,000
- [ ] `.env`에서 `MANAGEMENT_EXECUTION_MODE=live` **한 줄만** 변경 → 파일 눈으로 재확인 → 서버 재기동
- [ ] 데모 실집행 **1회만**: 챗 카드 확인 → 집행 → Meta 광고관리자에서 감액·증액 반영 교차 확인
- [ ] 실패·`indeterminate` 응답 시: **그 자리에서 재시도 금지** → dry_run 복귀 → Meta 실측 확인 먼저
- [ ] 발표 종료 즉시: `MANAGEMENT_EXECUTION_MODE=dry_run` 복귀 + 재기동 + 복귀 확인(정상 요청 1건 스냅샷 `mode: dry_run`) + 데모 캠페인 2개 일시중지

---

### Task 7: mock 데모 상태화 + 데모 정본 단일화 (부록 캡처 ①②③용)

**배경** — 데모 캠페인 정본이 두 개(MockAdPlatform 100k/80k/60k vs `_CAMPAIGNS_DEMO` 40k/25k/15k/10k/10k)라 mock에서 리밸런스 적용이 drift 409로 막히고, mock writer(DRY_RUN)가 무동작이라 "예산이 움직인" 장면이 안 나온다. 단일 가변 스토어로 통일하고 mock writer가 스토어를 갱신하게 한다.

**Files:**
- Create: `backend/domain/management/adapters/demo_store.py` — 가변 데모 캠페인 스토어(싱글턴). 초기값 = 기존 `_CAMPAIGNS_DEMO` 5캠(이름·상태·예산·FaultMode 그대로). API: `campaigns()`(튜플 목록), `get_budget(cid) -> int`, `set_budget(cid, krw)`, `reset()`(테스트용). 첫 줄 한국어 헤더 주석.
- Modify: `backend/domain/management/adapters/mock.py` — `_DEMO_SCENARIOS` 예산을 스토어에서 읽게(camp_1~3 유지, 값은 스토어의 40k/25k/15k). `list_campaigns`·`get_metrics`의 예산 참조를 스토어 경유로.
- Modify: `backend/domain/management/wiring.py` — `build_writer`의 use_mock 분기에서 `DemoBudgetWriter(MetaAdsWriter(settings, mode=DRY_RUN))` 반환. `DemoBudgetWriter`는 demo_store.py(또는 mock.py)에 두는 얇은 위임 래퍼 — `adjust_budget`만 inner 호출 성공 시 `store.set_budget` 추가, 나머지 메서드는 `__getattr__` 위임.
- Modify: `backend/api/routers/management.py` — `_CAMPAIGNS_DEMO` 상수를 스토어 참조로 교체(소비처 4곳: `get_campaigns`·`get_campaign`·`_current_daily_budget` mock 분기·`_budget_status_demo`). 예산 숫자·5캠 구성은 불변이므로 화면·기존 데모 동작 유지.
- Test: `test/backend/management/test_demo_store.py` (신규) — ① 스토어 초기값=기존 값 ② set_budget 후 mock reader·`_current_daily_budget`이 같은 값 ③ DemoBudgetWriter.adjust_budget 성공 시 스토어 갱신·실패 시 미갱신.

- [ ] **Step 1: 실패하는 테스트 작성** (위 3케이스 — dict 리터럴, C408 금지)
- [ ] **Step 2: 구현** (스토어 → mock.py → wiring → 라우터 순)
- [ ] **Step 3: 전체 회귀** — `cd backend && uv run pytest -q`. `_CAMPAIGNS_DEMO`·mock 예산 숫자를 단언하는 기존 테스트가 있으면 값은 안 바뀌었으므로 통과해야 정상. MockAdPlatform 예산이 100k→40k대로 바뀌는 영향으로 mock 지표 절대값을 단언하는 테스트가 깨지면, 비율 기반 단언으로 고칠 수 있는 것만 고치고 판단이 필요한 건 보고.
- [ ] **Step 4: mock E2E 수동 검증 절차 출력** — USE_MOCK=true로 서버 켜고 budget 페이지에서 제안→적용→새로고침 시 예산 이동 확인(캡처 ①②③). 검증 후 USE_MOCK 원복.
- [ ] **Step 5: Ruff + 커밋** — `fix: mock 데모 정본 단일화 + 상태화 — 리밸런스 mock 적용 drift 409 해소`

---

### Task 6: 스펙 문서 커밋 (스펙이 아직 미커밋 상태면)

- [ ] Run: `git status --short docs/superpowers/specs/2026-07-11-rebalance-demo-package-design.md` — 미추적/변경이면 커밋.

```bash
git add docs/superpowers/specs/2026-07-11-rebalance-demo-package-design.md docs/superpowers/plans/2026-07-11-rebalance-demo-package.md
git commit -m "add: 발표 대비 리밸런스 데모 패키지 — 스펙·구현 계획"
```
