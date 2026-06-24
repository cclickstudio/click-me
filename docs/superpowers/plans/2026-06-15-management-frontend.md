# 광고 매니지먼트 프론트엔드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** management 도메인의 감지→진단→재생성→제안→승인→실행→감사 HITL 루프를, A·B 역할이 동등하게 보이는 균형 하이브리드 대시보드(`/manage`)로 구현하고, 사용자/아키텍처 토글을 제공한다.

**Architecture:** 백엔드는 기존 `GET /run`·`POST /approve`에 더해 B 소유 도메인에 위임하는 얇은 엔드포인트 3종(`POST /regenerate`·`POST /execute`·`GET /audit`)을 추가한다(인메모리·결정론 폴백, Mock). 프론트는 `app/manage/page.tsx`를 전면 교체해 좌우 2존(🅰 측정·진단 / 🅱 개선·실행) + 가운데 승인 다리(🤝) + 하단 감사로 구성하고, 사이클을 단계별 fetch로 진행한다.

**Tech Stack:** Backend FastAPI + pydantic v2 + pytest(TestClient). Frontend Next.js(App Router, TS) + Tailwind, 커스텀 SVG 차트(차트 라이브러리 추가 없음). 프론트는 단위 테스트 러너가 없어 `pnpm lint`·`pnpm build`(타입체크)로 검증한다.

---

## File Structure

**백엔드 (수정 1, 신규 0)**
- Modify: `backend/api/routers/management.py` — `/regenerate`·`/execute`·`/audit` 추가(얇은 위임). 판정·실행·재생성 로직은 전부 `domain.management`에 위임.
- Test: `backend/tests/management/test_management_router.py` — 신규, 5엔드포인트 왕복.

**프론트엔드 (신규 7, 수정 2)**
- Modify: `frontend/src/lib/api.ts` — `management` 네임스페이스 추가.
- Create: `frontend/src/components/manage/types.ts` — API 응답 TS 타입.
- Create: `frontend/src/components/manage/KpiStrip.tsx`
- Create: `frontend/src/components/manage/AZone.tsx` — ImpressionTrendChart + SpendTrendChart + DiagnosisCard (🅰)
- Create: `frontend/src/components/manage/BZone.tsx` — CandidateCards + ProposalCard + ExecutionResult (🅱)
- Create: `frontend/src/components/manage/ApprovalBridge.tsx` — 승인(🤝)
- Create: `frontend/src/components/manage/AuditTimeline.tsx` — 감사(🤝)
- Create: `frontend/src/components/manage/RoleTag.tsx` — 아키텍처 보기 시 🅰/🅱/🤝·계약 라벨
- Modify: `frontend/src/app/manage/page.tsx` — 전면 교체(사이클 오케스트레이션 + 토글 + 디스클레이머)

**데모 상수(재사용)**: `domain/management/demo.py`의 `CAMPAIGN_ID`·`TENANT_ID`, `contracts/policy.py`의 `DAILY_BUDGET_KRW`·`APPROVAL_POLICY_VERSION`.

---

## Task 1: 백엔드 `POST /regenerate` (재생성 → ActionProposal)

**Files:**
- Modify: `backend/api/routers/management.py`
- Test: `backend/tests/management/test_management_router.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/management/test_management_router.py`:
```python
"""management 라우터 — /run→/regenerate→/approve→/execute→/audit 왕복."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import management


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(management.router, prefix="/api/management")
    return TestClient(app)


def test_regenerate_returns_replace_creative_proposal(client):
    run = client.get("/api/management/run?fault=bid_loss").json()
    assert run["diagnosis"] is not None

    res = client.post("/api/management/regenerate", json={"diagnosis": run["diagnosis"]})
    assert res.status_code == 200
    proposal = res.json()["proposal"]
    assert proposal["action_type"] == "REPLACE_CREATIVE"
    assert proposal["evidence_metrics"]["selected_candidate_id"]
    assert len(proposal["evidence_metrics"]["candidates"]) >= 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_management_router.py::test_regenerate_returns_replace_creative_proposal -v`
Expected: FAIL (404 — `/regenerate` 미구현)

- [ ] **Step 3: 엔드포인트 구현**

`backend/api/routers/management.py` 상단 import에 추가:
```python
from domain.management.agents.regeneration import RegenerationContext
from domain.management.agents.regeneration_tools import build_regeneration_agent
from domain.management.contracts.schemas import ApprovedAction, DiagnosisResult
```
(`ActionProposal`은 이미 import됨.)

파일 끝에 추가:
```python
class RegenerateRequest(BaseModel):
    diagnosis: DiagnosisResult


@router.post("/regenerate")
async def regenerate(body: RegenerateRequest):
    """🅱 재생성 agent — 진단 수신 → 후보 생성·채점 → REPLACE_CREATIVE 제안 패키징."""
    agent = build_regeneration_agent()  # API 키 없으면 결정론 폴백
    context = RegenerationContext(
        ad_account_id="act_demo_001",
        target_object_ids=(body.diagnosis.campaign_id,),
        budget_before_krw=DAILY_BUDGET_KRW,
        budget_after_krw=int(DAILY_BUDGET_KRW * 1.5),
        run_days=7,
        expected_state_version="state_v1",
        approval_policy_version=APPROVAL_POLICY_VERSION,
        action_type="REPLACE_CREATIVE",
    )
    proposal = await agent.propose(body.diagnosis, context)
    if proposal is None:
        raise HTTPException(status_code=422, detail="생존 후보 없음 — 재생성 빈손")
    return {"proposal": proposal.model_dump(mode="json")}
```
`APPROVAL_POLICY_VERSION`을 policy import에 추가:
```python
from domain.management.contracts.policy import APPROVAL_POLICY_VERSION, DAILY_BUDGET_KRW
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_management_router.py::test_regenerate_returns_replace_creative_proposal -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/api/routers/management.py backend/tests/management/test_management_router.py
git commit -m "add: management /regenerate 엔드포인트 (재생성 agent 위임)"
```

---

## Task 2: 백엔드 `POST /execute` (executor 실행 → ActionResult)

**Files:**
- Modify: `backend/api/routers/management.py`
- Test: `backend/tests/management/test_management_router.py`

- [ ] **Step 1: 실패 테스트 작성** (위 테스트 파일에 함수 추가)

```python
def test_full_cycle_run_regenerate_approve_execute(client):
    run = client.get("/api/management/run?fault=bid_loss").json()
    proposal = client.post(
        "/api/management/regenerate", json={"diagnosis": run["diagnosis"]}
    ).json()["proposal"]

    approved = client.post(
        "/api/management/approve",
        json={"proposal": proposal, "approved": True, "approver_id": "user_demo"},
    ).json()
    assert approved["status"] == "approved"
    action = approved["approved_action"]

    res = client.post(
        "/api/management/execute", json={"approved_action": action, "proposal": proposal}
    )
    assert res.status_code == 200
    result = res.json()["result"]
    assert result["status"] in ("success", "pending_review")
    assert result["approval_id"] == action["approval_id"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_management_router.py::test_full_cycle_run_regenerate_approve_execute -v`
Expected: FAIL (404 — `/execute` 미구현)

- [ ] **Step 3: executor 조립 + 엔드포인트 구현**

`backend/api/routers/management.py` import 추가:
```python
from domain.management.adapters.meta.writer import MetaAdsWriter
from domain.management.execution.audit_log import InMemoryAuditLog
from domain.management.execution.executor import Executor, InMemoryIdempotencyStore
from domain.management.execution.tier import TenantBudgetRegistry
```

모듈 수준 싱글턴(파일 상단 `router = APIRouter()` 아래)에 추가:
```python
# 데모용 인메모리 상태 — core 테이블 합의 후 DB Sink로 교체 (합의문서 §7)
_AUDIT_LOG = InMemoryAuditLog()
_BUDGET = TenantBudgetRegistry(default_limit_krw=10_000_000)
_executor: Executor | None = None


async def _state_version(_ad_account_id: str) -> str:
    return "state_v1"  # 데모 고정 — 제안의 expected_state_version과 일치


def _get_executor() -> Executor:
    global _executor  # noqa: PLW0603
    if _executor is None:
        _executor = Executor(
            MetaAdsWriter(),
            idempotency=InMemoryIdempotencyStore(),
            audit=_AUDIT_LOG,
            budget_for=_BUDGET.for_tenant,
            state_version_provider=_state_version,
            current_policy_version=APPROVAL_POLICY_VERSION,
        )
    return _executor
```

파일 끝에 추가:
```python
class ExecuteRequest(BaseModel):
    approved_action: ApprovedAction
    proposal: ActionProposal


@router.post("/execute")
async def execute(body: ExecuteRequest):
    """🅱 executor — 승인 후 4단계 재검증 + 멱등 실행. 모든 지출 단일 경로."""
    result = await _get_executor().execute(body.approved_action, body.proposal)
    return {"result": result.model_dump(mode="json")}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/management/test_management_router.py::test_full_cycle_run_regenerate_approve_execute -v`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add backend/api/routers/management.py backend/tests/management/test_management_router.py
git commit -m "add: management /execute 엔드포인트 (멱등 executor 위임)"
```

---

## Task 3: 백엔드 `GET /audit` (감사 로그 조회)

**Files:**
- Modify: `backend/api/routers/management.py`
- Test: `backend/tests/management/test_management_router.py`

- [ ] **Step 1: 실패 테스트 작성** (테스트 파일에 추가)

```python
def test_audit_lists_events_for_approval(client):
    run = client.get("/api/management/run?fault=bid_loss").json()
    proposal = client.post(
        "/api/management/regenerate", json={"diagnosis": run["diagnosis"]}
    ).json()["proposal"]
    action = client.post(
        "/api/management/approve",
        json={"proposal": proposal, "approved": True, "approver_id": "user_demo"},
    ).json()["approved_action"]
    client.post("/api/management/execute", json={"approved_action": action, "proposal": proposal})

    res = client.get(f"/api/management/audit?approval_id={action['approval_id']}")
    assert res.status_code == 200
    events = res.json()["events"]
    assert any(e["category"] == "executor.completed" for e in events)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd backend && uv run pytest tests/management/test_management_router.py::test_audit_lists_events_for_approval -v`
Expected: FAIL (404)

- [ ] **Step 3: 엔드포인트 구현** (파일 끝에 추가)

```python
@router.get("/audit")
async def get_audit(approval_id: str):
    """승인 단위 감사 이벤트(append-only) — 게이트 #7 추적용."""
    events = _AUDIT_LOG.for_approval(approval_id)
    return {
        "events": [
            {
                "event_id": e.event_id,
                "category": e.category,
                "occurred_at": e.occurred_at.isoformat(),
                "payload": e.payload,
            }
            for e in events
        ]
    }
```

- [ ] **Step 4: 테스트 통과 + 전체 회귀 확인**

Run: `cd backend && uv run pytest tests/management -q`
Expected: PASS (기존 92 + 신규 3)

- [ ] **Step 5: Ruff + 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
cd .. && git add backend/api/routers/management.py backend/tests/management/test_management_router.py
git commit -m "add: management /audit 엔드포인트 (감사 로그 조회)"
```

---

## Task 4: 프론트 API 클라이언트 + 타입

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/components/manage/types.ts`

- [ ] **Step 1: 타입 정의**

`frontend/src/components/manage/types.ts`:
```ts
// 매니지먼트 API 응답 타입 — 백엔드 contracts/schemas.py 대응

export type Snapshot = { as_of: string; impressions: number; spend_krw: number };

export type Diagnosis = {
  diagnosis_id: string;
  tenant_id: string;
  campaign_id: string;
  anomaly_type: string;
  source: "deterministic" | "agent";
  hypothesis: string;
  confidence: number;
  evidence_metrics: Record<string, unknown>;
  metrics_as_of: string;
  status: string;
};

export type Candidate = { candidate_id: string; sim_score: number | null; preview_url: string | null };

export type Proposal = {
  proposal_id: string;
  tenant_id: string;
  action_type: string;
  action_tier: number;
  evidence_metrics: { candidates?: Candidate[]; selected_candidate_id?: string } & Record<string, unknown>;
  budget_before_krw: number;
  budget_after_krw: number;
  max_total_spend_krw: number;
  expires_at: string;
  proposal_hash: string;
  confidence: number;
  status: string;
};

export type RunResult = {
  fault: string;
  expected: number[];
  snapshots: Snapshot[];
  anomaly_hours: number[];
  diagnosis: Diagnosis | null;
  proposal: Proposal | null;
  relabeled: boolean;
  requires_human: boolean;
  validation_issues: string[];
};

export type ApprovedAction = { approval_id: string; action_tier: number; [k: string]: unknown };
export type ActionResult = {
  result_id: string;
  approval_id: string;
  status: string;
  failure_reason: string | null;
  idempotency_key: string;
};
export type AuditEvent = { event_id: string; category: string; occurred_at: string; payload: Record<string, unknown> };

export type ViewMode = "user" | "arch";
```

- [ ] **Step 2: api.ts에 management 네임스페이스 추가**

`frontend/src/lib/api.ts`의 `generator: {` 블록 바로 위에 추가:
```ts
  management: {
    run: (fault: string) =>
      request(`/management/run?fault=${fault}`),
    regenerate: (diagnosis: unknown) =>
      request("/management/regenerate", { method: "POST", body: JSON.stringify({ diagnosis }) }),
    approve: (proposal: unknown, approved: boolean) =>
      request("/management/approve", {
        method: "POST",
        body: JSON.stringify({ proposal, approved, approver_id: "user_demo" }),
      }),
    execute: (approved_action: unknown, proposal: unknown) =>
      request("/management/execute", {
        method: "POST",
        body: JSON.stringify({ approved_action, proposal }),
      }),
    audit: (approvalId: string) => request(`/management/audit?approval_id=${approvalId}`),
  },
```

- [ ] **Step 3: 타입체크 확인**

Run: `cd frontend && pnpm build`
Expected: PASS (컴파일 성공)

- [ ] **Step 4: 커밋**

```bash
git add frontend/src/lib/api.ts frontend/src/components/manage/types.ts
git commit -m "add: 매니지먼트 프론트 API 클라이언트·타입"
```

---

## Task 5: RoleTag + KpiStrip

**Files:**
- Create: `frontend/src/components/manage/RoleTag.tsx`
- Create: `frontend/src/components/manage/KpiStrip.tsx`

- [ ] **Step 1: RoleTag 구현** (아키텍처 보기에서만 표시되는 소유자/계약 배지)

`frontend/src/components/manage/RoleTag.tsx`:
```tsx
// 아키텍처 보기 전용 소유자(🅰/🅱/🤝)·계약 라벨 — 사용자 보기에선 렌더 안 함
import type { ViewMode } from "./types";

const COLORS: Record<string, string> = { A: "#3182F6", B: "#0F9D58", "AB": "#8B95A1" };

export function RoleTag({ mode, role, contract }: { mode: ViewMode; role: "A" | "B" | "AB"; contract?: string }) {
  if (mode !== "arch") return null;
  const label = role === "A" ? "🅰" : role === "B" ? "🅱" : "🤝";
  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-semibold" style={{ color: COLORS[role] }}>
      {label}{contract ? <span className="text-[#8B95A1]">· {contract}</span> : null}
    </span>
  );
}
```

- [ ] **Step 2: KpiStrip 구현**

`frontend/src/components/manage/KpiStrip.tsx`:
```tsx
// 상단 KPI 4종 — 활성 캠페인·오늘 노출·오늘 지출·이상 감지
import type { RunResult } from "./types";

export function KpiStrip({ run }: { run: RunResult | null }) {
  const impressions = run?.snapshots.reduce((a, s) => a + s.impressions, 0) ?? 0;
  const spend = run?.snapshots.reduce((a, s) => a + s.spend_krw, 0) ?? 0;
  const anomalies = run?.anomaly_hours.length ? 1 : 0;
  const cards = [
    { label: "활성 캠페인", value: "1" },
    { label: "오늘 노출", value: impressions.toLocaleString() },
    { label: "오늘 지출", value: `₩${spend.toLocaleString()}` },
    { label: "이상 감지", value: String(anomalies), alert: anomalies > 0 },
  ];
  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      {cards.map((c) => (
        <div key={c.label} className={`bg-white dark:bg-[#1C2333] border rounded-2xl p-5 ${c.alert ? "border-[#E5484D]" : "border-[#E5E8EB] dark:border-[#2D3748]"}`}>
          <p className="text-xs text-[#8B95A1] mb-1">{c.label}</p>
          <p className={`text-2xl font-bold ${c.alert ? "text-[#E5484D]" : "text-[#191F28] dark:text-[#F2F4F6]"}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 타입체크 + 커밋**

```bash
cd frontend && pnpm build
cd .. && git add frontend/src/components/manage/RoleTag.tsx frontend/src/components/manage/KpiStrip.tsx
git commit -m "add: 매니지먼트 RoleTag·KpiStrip"
```

---

## Task 6: A존 (측정·진단) — 차트 + 진단 카드

**Files:**
- Create: `frontend/src/components/manage/AZone.tsx`

- [ ] **Step 1: AZone 구현** (커스텀 SVG 노출 곡선 + 지출 막대 + 진단 카드)

`frontend/src/components/manage/AZone.tsx`:
```tsx
// 🅰 측정·진단 존 — 기대 vs 실측 노출 곡선(이상구간 음영) + 지출 막대 + 진단 카드
import type { RunResult, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

function ImpressionChart({ run }: { run: RunResult }) {
  const w = 320, h = 90, n = run.expected.length || 1;
  const max = Math.max(1, ...run.expected, ...run.snapshots.map((s) => s.impressions));
  const x = (i: number) => (i / (n - 1)) * w;
  const y = (v: number) => h - (v / max) * h;
  const line = (vals: number[]) => vals.map((v, i) => `${i === 0 ? "M" : "L"}${x(i)},${y(v)}`).join(" ");
  const actual = run.snapshots.map((s) => s.impressions);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-24">
      {run.anomaly_hours.map((hr) => (
        <rect key={hr} x={x(hr) - 3} y={0} width={6} height={h} fill="#E5484D" opacity={0.12} />
      ))}
      <path d={line(run.expected)} fill="none" stroke="#3182F6" strokeWidth={1.5} strokeDasharray="4 3" />
      <path d={line(actual)} fill="none" stroke="#3182F6" strokeWidth={2} />
    </svg>
  );
}

export function AZone({ run, mode }: { run: RunResult; mode: ViewMode }) {
  const dx = run.diagnosis;
  return (
    <section className="flex-1 border rounded-2xl p-5 border-[#3182F6]/40 bg-[#3182F6]/[0.03]">
      <h2 className="text-sm font-bold text-[#3182F6] mb-3 flex items-center gap-2">
        📊 측정 · 진단 <RoleTag mode={mode} role="A" />
      </h2>
      <p className="text-xs text-[#8B95A1] mb-1">노출 추이 · 기대모델 vs 실측</p>
      <ImpressionChart run={run} />
      {dx && (
        <div className="mt-3 rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">🔍 {dx.hypothesis || dx.anomaly_type}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#F2F4F6] dark:bg-[#252D3D] text-[#8B95A1]">{dx.source}</span>
          </div>
          <p className="text-xs text-[#8B95A1] mt-1">확신도 {Math.round(dx.confidence * 100)}%</p>
          <RoleTag mode={mode} role="A" contract="DiagnosisResult ▶" />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: 타입체크 + 커밋**

```bash
cd frontend && pnpm build
cd .. && git add frontend/src/components/manage/AZone.tsx
git commit -m "add: 매니지먼트 A존(측정·진단) 컴포넌트"
```

---

## Task 7: B존 (개선·실행) — 후보 + 제안 + 실행 결과

**Files:**
- Create: `frontend/src/components/manage/BZone.tsx`

- [ ] **Step 1: BZone 구현**

`frontend/src/components/manage/BZone.tsx`:
```tsx
// 🅱 개선·실행 존 — 재생성 후보 + 제안 카드 + 실행 결과
import type { ActionResult, Proposal, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

export function BZone({
  proposal,
  result,
  mode,
}: {
  proposal: Proposal | null;
  result: ActionResult | null;
  mode: ViewMode;
}) {
  const candidates = proposal?.evidence_metrics.candidates ?? [];
  const selected = proposal?.evidence_metrics.selected_candidate_id;
  return (
    <section className="flex-1 border rounded-2xl p-5 border-[#0F9D58]/40 bg-[#0F9D58]/[0.03]">
      <h2 className="text-sm font-bold text-[#0F9D58] mb-3 flex items-center gap-2">
        ✨ 개선 · 실행 <RoleTag mode={mode} role="B" />
      </h2>

      <p className="text-xs text-[#8B95A1] mb-2">🎨 재생성 후보 (시뮬 점수는 실성과 상관 미검증·참고용)</p>
      <div className="grid grid-cols-3 gap-2 mb-3">
        {candidates.map((c) => (
          <div key={c.candidate_id} className={`rounded-lg border p-2 text-center ${c.candidate_id === selected ? "border-[#0F9D58] bg-[#0F9D58]/10" : "border-[#E5E8EB] dark:border-[#2D3748]"}`}>
            <p className="text-[10px] text-[#8B95A1] truncate">{c.candidate_id.slice(0, 6)}</p>
            <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6]">{c.sim_score?.toFixed(2) ?? "-"}</p>
            {c.candidate_id === selected && <p className="text-[10px] text-[#0F9D58]">✓ 선택</p>}
          </div>
        ))}
      </div>

      {proposal && (
        <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] p-3 mb-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">📋 {proposal.action_type}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-[#FFF3E0] text-[#E5840F]">Tier {proposal.action_tier}</span>
          </div>
          <p className="text-xs text-[#8B95A1] mt-1">
            예산 ₩{proposal.budget_before_krw.toLocaleString()} ▶ ₩{proposal.budget_after_krw.toLocaleString()}
          </p>
          <RoleTag mode={mode} role="B" contract="◀ ActionProposal" />
        </div>
      )}

      {result && (
        <div className={`rounded-xl border p-3 ${result.status === "failed" || result.status === "rejected" ? "border-[#E5484D]" : "border-[#0F9D58]"}`}>
          <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6]">
            ⚙ 실행 결과: {result.status}{result.failure_reason ? ` (${result.failure_reason})` : ""}
          </p>
          <RoleTag mode={mode} role="B" contract="ActionResult ▶" />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: 타입체크 + 커밋**

```bash
cd frontend && pnpm build
cd .. && git add frontend/src/components/manage/BZone.tsx
git commit -m "add: 매니지먼트 B존(개선·실행) 컴포넌트"
```

---

## Task 8: 승인 다리 + 감사 타임라인

**Files:**
- Create: `frontend/src/components/manage/ApprovalBridge.tsx`
- Create: `frontend/src/components/manage/AuditTimeline.tsx`

- [ ] **Step 1: ApprovalBridge 구현**

`frontend/src/components/manage/ApprovalBridge.tsx`:
```tsx
// 🤝 승인(HITL) — Tier 판정·재라벨=A 설계 / 무승인 차단=B 강제. 공동 클라이맥스.
import type { RunResult, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

export function ApprovalBridge({
  run,
  decided,
  onApprove,
  onReject,
  mode,
}: {
  run: RunResult | null;
  decided: "approved" | "rejected" | null;
  onApprove: () => void;
  onReject: () => void;
  mode: ViewMode;
}) {
  return (
    <div className="my-6 rounded-2xl border-2 border-[#3182F6] p-4 text-center bg-gradient-to-r from-[#3182F6]/[0.05] to-[#0F9D58]/[0.05]">
      <p className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] mb-1">
        🤝 승인 (HITL) <RoleTag mode={mode} role="AB" contract="ApprovedAction ▶" />
      </p>
      {run?.relabeled && <p className="text-xs text-[#E5840F] mb-2">⚠ Tier 1▶3 재라벨됨 — 사용자 승인 필요</p>}
      {decided === null ? (
        <div className="flex items-center justify-center gap-3">
          <button onClick={onApprove} disabled={!run?.proposal} className="px-5 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40">적용 승인</button>
          <button onClick={onReject} disabled={!run?.proposal} className="px-5 py-2 border border-[#E5E8EB] dark:border-[#2D3748] text-sm rounded-lg disabled:opacity-40">거절</button>
        </div>
      ) : (
        <p className="text-sm font-medium text-[#8B95A1]">{decided === "approved" ? "✅ 승인됨" : "🚫 거절됨 — 무승인 액션은 어떤 경로로도 적용되지 않습니다"}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: AuditTimeline 구현**

`frontend/src/components/manage/AuditTimeline.tsx`:
```tsx
// 🤝 감사 로그 — append-only 이벤트 타임라인
import type { AuditEvent, ViewMode } from "./types";
import { RoleTag } from "./RoleTag";

export function AuditTimeline({ events, mode }: { events: AuditEvent[]; mode: ViewMode }) {
  if (events.length === 0) return null;
  return (
    <div className="mt-6 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4">
      <p className="text-sm font-semibold text-[#191F28] dark:text-[#F2F4F6] mb-2">🧾 감사 로그 <RoleTag mode={mode} role="AB" /></p>
      <ul className="space-y-1">
        {events.map((e) => (
          <li key={e.event_id} className="text-xs text-[#8B95A1] flex gap-2">
            <span className="text-[#B0B8C1]">{new Date(e.occurred_at).toLocaleTimeString("ko-KR")}</span>
            <span className="font-mono">{e.category}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 3: 타입체크 + 커밋**

```bash
cd frontend && pnpm build
cd .. && git add frontend/src/components/manage/ApprovalBridge.tsx frontend/src/components/manage/AuditTimeline.tsx
git commit -m "add: 매니지먼트 승인 다리·감사 타임라인"
```

---

## Task 9: page.tsx 전면 교체 (사이클 오케스트레이션 + 토글)

**Files:**
- Modify: `frontend/src/app/manage/page.tsx`

- [ ] **Step 1: 페이지 전체 교체**

`frontend/src/app/manage/page.tsx` 전체를 아래로 교체:
```tsx
'use client';

import { useState } from 'react';
import AppLayout from '@/components/AppLayout';
import { api } from '@/lib/api';
import { AZone } from '@/components/manage/AZone';
import { BZone } from '@/components/manage/BZone';
import { ApprovalBridge } from '@/components/manage/ApprovalBridge';
import { AuditTimeline } from '@/components/manage/AuditTimeline';
import { KpiStrip } from '@/components/manage/KpiStrip';
import type { ActionResult, AuditEvent, RunResult, ViewMode } from '@/components/manage/types';

const FAULTS = ['bid_loss', 'review_rejected', 'none'];

export default function Page() {
  const [mode, setMode] = useState<ViewMode>('user');
  const [fault, setFault] = useState('bid_loss');
  const [run, setRun] = useState<RunResult | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [decided, setDecided] = useState<'approved' | 'rejected' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    setBusy(true); setError(null); setResult(null); setAudit([]); setDecided(null);
    try {
      const r = (await api.management.run(fault)) as RunResult;
      if (r.diagnosis) {
        const { proposal } = (await api.management.regenerate(r.diagnosis)) as { proposal: RunResult['proposal'] };
        r.proposal = proposal;
      }
      setRun(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : '실행 실패');
    } finally { setBusy(false); }
  };

  const approve = async () => {
    if (!run?.proposal) return;
    setBusy(true); setError(null);
    try {
      const a = (await api.management.approve(run.proposal, true)) as { approved_action: { approval_id: string } };
      setDecided('approved');
      const { result: res } = (await api.management.execute(a.approved_action, run.proposal)) as { result: ActionResult };
      setResult(res);
      const { events } = (await api.management.audit(a.approved_action.approval_id)) as { events: AuditEvent[] };
      setAudit(events);
    } catch (e) {
      setError(e instanceof Error ? e.message : '승인·실행 실패');
    } finally { setBusy(false); }
  };

  const reject = async () => {
    if (!run?.proposal) return;
    await api.management.approve(run.proposal, false);
    setDecided('rejected');
  };

  return (
    <AppLayout>
      <div className="max-w-screen-xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-bold text-[#191F28] dark:text-[#F2F4F6]">광고 매니지먼트</h1>
            <p className="text-sm text-[#8B95A1] mt-1">집행 후 이상 감지부터 개선·실행까지 (Mock 기반 데모)</p>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden text-sm">
              <button onClick={() => setMode('user')} className={`px-3 py-1.5 ${mode === 'user' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}>사용자 보기</button>
              <button onClick={() => setMode('arch')} className={`px-3 py-1.5 ${mode === 'arch' ? 'bg-[#3182F6] text-white' : 'text-[#8B95A1]'}`}>아키텍처 보기</button>
            </div>
            <select value={fault} onChange={(e) => setFault(e.target.value)} className="text-sm px-2 py-1.5 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent">
              {FAULTS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
            <button onClick={start} disabled={busy} className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40">
              {busy ? '실행 중…' : '▶ 데모 실행'}
            </button>
          </div>
        </div>

        <KpiStrip run={run} />

        {run ? (
          <>
            <div className="flex flex-col lg:flex-row gap-4 items-stretch">
              <AZone run={run} mode={mode} />
              <BZone proposal={run.proposal} result={result} mode={mode} />
            </div>
            <ApprovalBridge run={run} decided={decided} onApprove={approve} onReject={reject} mode={mode} />
            <AuditTimeline events={audit} mode={mode} />
          </>
        ) : (
          <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] py-20 text-center text-sm text-[#8B95A1]">
            "데모 실행"을 눌러 감지→진단→개선→승인→실행 사이클을 시작하세요
          </div>
        )}

        {error && <p className="mt-4 text-sm text-red-500" role="alert">{error}</p>}
        <p className="mt-6 text-[11px] text-[#B0B8C1]">⚠ Mock 기반 데모 · 시뮬 점수는 실제 성과와 상관 미검증 · 예측 CTR 등 실측 환산 없음 · 금액 KRW</p>
      </div>
    </AppLayout>
  );
}
```

- [ ] **Step 2: 타입체크 + 린트**

Run: `cd frontend && pnpm build && pnpm lint`
Expected: PASS

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/app/manage/page.tsx
git commit -m "add: 매니지먼트 대시보드 페이지(2존+승인+감사, 사용자/아키텍처 토글)"
```

---

## Task 10: E2E 수동 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: 백엔드 전체 테스트**

Run: `cd backend && uv run pytest tests/management -q`
Expected: PASS (95)

- [ ] **Step 2: 프론트 빌드/린트**

Run: `cd frontend && pnpm lint && pnpm build`
Expected: PASS

- [ ] **Step 3: 수동 사이클 확인**

1. 백엔드 기동: `cd backend && uv run uvicorn api.main:app --reload --port 8000`
2. 프론트 기동: `cd frontend && pnpm dev`
3. `http://localhost:3000/manage` 접속(localhost 필수 — 비-localhost는 NEXT_PUBLIC_API_URL·CORS 필요).
4. 고장 `bid_loss` + "데모 실행" → A존 곡선 이상구간·진단, B존 후보3·제안 표시 확인.
5. "적용 승인" → B존 실행 결과 success + 감사 로그에 `executor.completed` 표시 확인.
6. "아키텍처 보기" 토글 → 🅰/🅱/🤝·계약 라벨이 양 존·승인·감사에 노출 확인.

- [ ] **Step 4: 최종 커밋(있으면)**

```bash
git add -A && git commit -m "chore: 매니지먼트 프론트 검증 완료"
```

---

## 비고

- `api/routers/management.py`는 🤝 공동 + 오케스트레이터 오너 TBD — 엔드포인트 3종 추가 전 A와 한 줄 합의 권장(합의문서 §6).
- 인메모리 상태(`_AUDIT_LOG`·`_BUDGET`·executor)는 데모용. core 5테이블 합의 후 DB Sink/Store로 교체(합의문서 §7).
- A 소유 파일(`detection/`·`approval.py`·`agents/diagnosis.py`)은 읽기만 — 수정 금지.
- spec의 `SpendTrendChart`는 v1에서 KpiStrip의 "오늘 지출"로 흡수(YAGNI). 일자별 지출 막대가 필요해지면 AZone에 별도 컴포넌트로 추가.
