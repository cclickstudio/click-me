# 챗 인라인 REPLACE_CREATIVE 흐름 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 챗에서 "○○ 캠페인 소재 바꿔줘" → generation·후보 선택 → 영향 광고 프리뷰 → 승인 → 집행까지 한 세션에서 완주하는 흐름을 mock 모드로 완성한다.

**Architecture:** 백엔드 REPLACE_CREATIVE 체인(proposal·approve·execute 엔드포인트)은 이미 존재한다. 신규는 (a) 챗 tool `replace_creative` + 위젯 헬퍼(백엔드), (b) 후보 picker→프리뷰→승인→집행을 담는 프론트 카드 `ChatReplaceCreativeCard`, (c) api 클라이언트 메서드. 기존 `manage_campaign` tool / `ChatBudgetProposalCard` / `GenResultWidget` 패턴을 그대로 따른다.

**Tech Stack:** Python(uv)·FastAPI·LangGraph @tool · Next.js(TS)·React · pytest.

**참조 스펙:** `docs/superpowers/specs/2026-07-07-chat-replace-creative-inline-flow-design.md`

**기존 백엔드 방어(계획에서 새로 안 만듦, 검증만):**
- **live 실집행 차단** — `/replace-creative-proposal`이 `_is_sending_mode()`(validate/live)면 **proposal 생성 단계에서 501**(management.py:2374). 즉 backend가 live여도 카드는 proposal조차 못 받고 501 에러만 보여, approve/execute 경로로 절대 못 넘어간다. 프론트 env 배지 불요.
- **후보 org 소유권** — `get_candidate`가 `X-Org-Id` 스코프라 타 org generation은 404(B-1 Task 0). 카드가 완료 generation 전체를 나열해도 타 org 후보는 백엔드가 막는다.

---

## 파일 구조

- **Modify** `backend/domain/chat/widgets.py` — `replace_creative_form(campaign_id)` 헬퍼 추가.
- **Modify** `backend/api/assistant/subagent_tools.py` — `@tool replace_creative` 추가 + 반환 tool 리스트에 등록.
- **Modify** `backend/api/assistant/prompts.py` — tool 설명 한 줄 추가.
- **Modify** `test/backend/chat/test_tools.py` — `replace_creative` tool 골든 테스트.
- **Modify** `frontend/src/lib/api.ts` — `replaceCreativeProposal(campaignId, body)` 메서드.
- **Create** `frontend/src/components/chat/ChatReplaceCreativeCard.tsx` — 후보 picker→프리뷰→승인→집행 카드.
- **Modify** `frontend/src/components/chat/ChatConversation.tsx` — `widget.type === 'replace_creative'` dispatch 블록.

> 백엔드 `.py` 수정 후 커밋 전 Ruff 제안(루트 CLAUDE.md). 커밋은 `add`/`edit`/`fix` 한국어 컨벤션.

---

## Task 1: 백엔드 — 위젯 헬퍼

**Files:**
- Modify: `backend/domain/chat/widgets.py`

- [ ] **Step 1: 위젯 헬퍼 추가** (`widgets.py` 맨 끝, `campaign_action` 아래)

campaign_name도 실어 카드가 이름→id 해석에 쓴다(예산 카드와 동일 — LLM은 이름만 알 때가 많다).

```python
def replace_creative_form(campaign_id: str = "", campaign_name: str = "") -> dict:
    """소재 교체 후보 picker 카드 — data={campaign_id, campaign_name}. source 고정.

    campaign_id/campaign_name 둘 다 비어도 카드가 캠페인 picker를 띄운다(빈 값 허용).
    """
    return {
        "widget": {
            "type": "replace_creative",
            "data": {"campaign_id": campaign_id, "campaign_name": campaign_name},
        },
        "source": DEEP_AGENT,
    }
```

- [ ] **Step 2: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/domain/chat/widgets.py
git commit -m "add: replace_creative_form 위젯 헬퍼 — 소재 교체 후보 picker 신호"
```

---

## Task 2: 백엔드 — 챗 tool `replace_creative` (TDD)

**Files:**
- Test: `test/backend/chat/test_tools.py`
- Modify: `backend/api/assistant/subagent_tools.py`

- [ ] **Step 1: 실패 테스트 작성** (`test_tools.py` 맨 끝에 추가 — id 있는 경우 + 빈 경우 둘 다)

```python
@pytest.mark.asyncio
async def test_replace_creative_emits_widget(tools):
    cmd = await _run(tools, "replace_creative", campaign_id="camp_1", campaign_name="여름")
    assert cmd.update["widget"] == {
        "type": "replace_creative",
        "data": {"campaign_id": "camp_1", "campaign_name": "여름"},
    }
    assert cmd.update["source"] == "deep-agent"


@pytest.mark.asyncio
async def test_replace_creative_emits_widget_without_id(tools):
    # campaign_id를 몰라도(이름만·둘 다 없음) 카드를 띄운다 — 해석/선택은 카드가 한다.
    cmd = await _run(tools, "replace_creative")
    assert cmd.update["widget"]["type"] == "replace_creative"
    assert cmd.update["widget"]["data"] == {"campaign_id": "", "campaign_name": ""}
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && uv run pytest -q -k test_replace_creative`
Expected: FAIL — `KeyError: 'replace_creative'`(tool 미등록)

- [ ] **Step 3: tool 구현** (`subagent_tools.py`, `manage_campaign`(line 930) 정의 아래에 추가)

campaign_id/name이 없어도 카드를 띄운다(카드가 캠페인 picker로 해석). 조기 반환 없음 —
예산 카드(`manage_campaign`)와 동일하게 "일단 카드를 띄우고 해석은 카드가".

```python
    @tool
    async def replace_creative(
        campaign_id: str = "",
        campaign_name: str = "",
        *,
        state: Annotated[dict, InjectedState],
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """기존 캠페인의 '광고 소재(이미지·카피)를 교체'해달라는 요청에 호출.
        내가 만든 광고 시안 후보를 고르는 picker 카드를 띄운다.
        캠페인을 알면 campaign_id 또는 campaign_name(이름만 알아도 됨)."""
        # 폼 시점 실행 히스토리 적재 — '요청' 기록(집행 확정은 executor가 별도 기록).
        helpers.spawn_record_execution(
            state.get("project_id"),
            "management",
            "replace_creative_request",
            f"소재 교체 요청(폼) 캠페인 {campaign_name or campaign_id or '(미지정)'}",
            {"campaign_id": campaign_id, "campaign_name": campaign_name, "stage": "request"},
        )
        return Command(
            update={
                **widgets.replace_creative_form(campaign_id, campaign_name),
                "messages": [
                    ToolMessage(
                        "소재 교체 후보를 고를 수 있는 카드를 준비했어요.",
                        tool_call_id=tool_call_id,
                    )
                ],
            }
        )
```

- [ ] **Step 4: tool 리스트에 등록** (`subagent_tools.py`, 반환 리스트의 `manage_campaign,`(line 1194) 바로 아래)

```python
        manage_campaign,
        replace_creative,
```

- [ ] **Step 5: 통과 확인**

Run: `cd backend && uv run pytest -q -k test_replace_creative`
Expected: PASS (2건)

- [ ] **Step 6: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/assistant/subagent_tools.py test/backend/chat/test_tools.py
git commit -m "add: 챗 replace_creative tool — 소재 교체 후보 picker 위젯 띄우기"
```

---

## Task 3: 백엔드 — 프롬프트에 tool 노출

**Files:**
- Modify: `backend/api/assistant/prompts.py`

- [ ] **Step 1: tool 설명 추가** (`prompts.py:68` — create_campaign/manage_campaign 안내 줄 아래에 한 줄 추가)

현재(line 68):
```
- '새 캠페인 만들기' → create_campaign. 기존 캠페인 '중지/게재/예산 변경' → manage_campaign.
```
바로 아래 줄 추가:
```
- 기존 캠페인 '소재(이미지·카피) 교체/바꾸기' → replace_creative.
```

- [ ] **Step 2: 라우팅 회귀 확인** (기존 tool 테스트가 안 깨지는지)

Run: `cd backend && uv run pytest -q test/backend/chat/`
Expected: PASS (전체 chat tool 테스트)

- [ ] **Step 3: 커밋**

```bash
cd backend && uv run ruff format . && uv run ruff check . --fix
git add backend/api/assistant/prompts.py
git commit -m "edit: 챗 프롬프트에 replace_creative tool 라우팅 안내 추가"
```

---

## Task 4: 프론트 — api 클라이언트 메서드

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: `replaceCreativeProposal` 추가** (`api.ts`, `management` 객체 안 `budgetCommit`(line 865) 아래에 추가)

```typescript
    replaceCreativeProposal: (
      campaignId: string,
      body: { generation_id: string; candidate_id: string; link_url: string },
    ) =>
      request<{
        proposal: Proposal;
        preview: {
          candidate: { headline?: string | null; body?: string | null; s3_key?: string | null };
          affected_ads: {
            ad_id: string;
            ad_name: string;
            thumbnail_url?: string | null;
            image_url?: string | null;
            headline?: string | null;
            primary_text?: string | null;
          }[];
        };
      }>(`/management/campaigns/${campaignId}/replace-creative-proposal`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
```

- [ ] **Step 2: 타입체크**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: 에러 없음 (Proposal은 이미 api.ts에서 import/정의됨 — budgetProposal이 사용 중)

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/lib/api.ts
git commit -m "add: replaceCreativeProposal api 클라이언트 — 후보→소재 교체 제안"
```

---

## Task 5: 프론트 — ChatReplaceCreativeCard

**Files:**
- Create: `frontend/src/components/chat/ChatReplaceCreativeCard.tsx`

- [ ] **Step 1: 카드 컴포넌트 작성** (신규 파일 전체)

```tsx
// 챗 임베드 소재 교체 — 캠페인 해석 → generation·후보 선택 → 영향 광고 프리뷰 → 승인·집행(mock).
'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ApiError, api } from '@/lib/api';
import type { CampaignSummary } from '@/components/manage/campaigns/types';
import type { Proposal, ActionResult } from '@/components/manage/types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';
// 도착 URL(랜딩) 기본값 — 사용자가 확인·수정한다(소재 교체가 도착지까지 바꾸지 않게 명시 입력).
// TODO(후속): 기존 광고 랜딩 URL을 읽어와 기본값으로 보존.
const DEFAULT_LINK = 'https://clickme.co.kr';

type PickItem = Pick<CampaignSummary, 'campaign_id' | 'name' | 'state'>;
type GenItem = { id: string; status: string; created_at?: string };
type Candidate = {
  candidate_id: string;
  idx: number;
  s3_key: string | null;
  image_url: string | null;
  copy: Record<string, string> | null;
  rank?: number | null;
};
type AffectedAd = {
  ad_id: string;
  ad_name: string;
  thumbnail_url?: string | null;
  image_url?: string | null;
};
type Preview = {
  candidate: { headline?: string | null; body?: string | null; s3_key?: string | null };
  affected_ads: AffectedAd[];
};

function candImg(c: Candidate): string | null {
  if (c.image_url) return c.image_url.startsWith('/') ? `${API_BASE}${c.image_url}` : c.image_url;
  if (c.s3_key) return `${API_BASE}/api/generator/image?key=${encodeURIComponent(c.s3_key)}`;
  return null;
}

const CARD = 'mt-1 rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-4 max-w-md';

export default function ChatReplaceCreativeCard({
  campaignId,
  campaignName,
}: {
  campaignId: string;
  campaignName?: string;
}) {
  const [picker, setPicker] = useState<PickItem[]>([]);
  const [resolvedId, setResolvedId] = useState('');
  const [warning, setWarning] = useState<string | null>(null);
  const [gens, setGens] = useState<GenItem[]>([]);
  const [genId, setGenId] = useState('');
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [linkUrl, setLinkUrl] = useState(DEFAULT_LINK);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<ActionResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 캠페인 해석 — LLM이 준 id/이름을 반드시 로그인 사용자의 캠페인 목록으로 재매칭(정본).
  // 예산 카드(ChatBudgetProposalCard)와 동일 규칙 — 못 찾으면 직접 선택하게 한다.
  useEffect(() => {
    let alive = true;
    api.management
      .campaigns()
      .then((r) => {
        if (!alive) return;
        const list = (r.campaigns ?? []).map((c) => ({
          campaign_id: c.campaign_id,
          name: c.name,
          state: c.state,
        }));
        setPicker(list);
        const canonical =
          (campaignId && list.find((c) => c.campaign_id === campaignId)) ||
          (campaignName && list.find((c) => c.name === campaignName)) ||
          null;
        if (canonical) {
          setResolvedId(canonical.campaign_id);
          setWarning(null);
        } else if (campaignId || campaignName) {
          setWarning('지정한 캠페인을 찾을 수 없어 직접 선택해 주세요.');
        }
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [campaignId, campaignName]);

  // 내 생성물 목록 로드 — 완료된 것만 후보가 있다.
  useEffect(() => {
    let alive = true;
    api.generator
      .list(20)
      .then((r) => {
        if (alive) setGens((r as GenItem[]).filter((g) => g.status === 'completed'));
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  // generation 선택 → 후보 로드.
  const onSelectGen = async (id: string) => {
    setGenId(id);
    setCandidates([]);
    setProposal(null);
    setPreview(null);
    setError(null);
    if (!id) return;
    try {
      const d = (await api.generator.detail(id)) as { candidates?: Candidate[] };
      setCandidates(d.candidates ?? []);
    } catch {
      setError('후보를 불러오지 못했어요.');
    }
  };

  // 후보 선택 → 제안 생성(프리뷰).
  const onPickCandidate = async (candidateId: string) => {
    if (!resolvedId) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.management.replaceCreativeProposal(resolvedId, {
        generation_id: genId,
        candidate_id: candidateId,
        link_url: linkUrl,
      });
      setProposal(r.proposal);
      setPreview(r.preview);
    } catch (e) {
      setError(e instanceof Error ? e.message : '제안을 만들지 못했어요.');
    } finally {
      setBusy(false);
    }
  };

  // 승인 → 집행. 프리뷰 화면에서 무엇이 바뀌는지 확인한 뒤 이 버튼 클릭이 곧 사람 승인(HITL).
  const approveAndReplace = async () => {
    if (!proposal) return;
    setBusy(true);
    setError(null);
    try {
      const approved = (await api.management.approve(proposal, true)) as {
        status: string;
        approved_action?: unknown;
        detail?: string;
      };
      if (approved.status !== 'approved' || !approved.approved_action) {
        setError(approved.detail ?? '승인이 거절됐어요.');
        return;
      }
      const resp = (await api.management.execute(approved.approved_action, proposal)) as {
        result?: ActionResult;
        error_message?: string;
      };
      if (resp.result) setResult(resp.result);
      if (resp.error_message) setError(resp.error_message);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 409 || e.status === 422)) {
        setProposal(null);
        setPreview(null);
        setError(e.message);
        return;
      }
      setError(e instanceof Error ? e.message : '집행에 실패했어요.');
    } finally {
      setBusy(false);
    }
  };

  // 결과 화면 — pending_review는 성공과 분리(아직 교체 완료 아님).
  if (result) {
    const pending = result.status === 'pending_review';
    const ok = result.status === 'success';
    return (
      <div className={CARD}>
        <p
          className={`font-bold ${ok || pending ? 'text-[#191F28] dark:text-[#F2F4F6]' : 'text-red-500'}`}
        >
          {pending ? '검토 대기 중' : ok ? '✓ 소재를 교체했어요' : '소재 교체 실패'}
        </p>
        {pending && <p className="mt-1 text-sm text-[#8B95A1]">Meta 검토가 진행 중이에요.</p>}
        {!ok && !pending && (
          <p className="mt-1 text-sm text-[#8B95A1]">
            {error ?? `사유 ${result.failure_reason ?? '알 수 없음'}`}
          </p>
        )}
        {(ok || pending) && result.approval_id && (
          <p className="mt-1 text-[11px] text-[#B0B8C1]">승인 ID {result.approval_id}</p>
        )}
        <Link
          href="/manage/campaigns"
          className="mt-3 inline-block px-3 py-1.5 bg-[#3182F6] text-white text-xs font-medium rounded-lg hover:bg-[#1B6EEB]"
        >
          대시보드로
        </Link>
      </div>
    );
  }

  // 프리뷰 + 승인 화면 — 새 소재 + 영향받는 광고(이름·썸네일)를 보여준 뒤 명시 승인.
  if (proposal && preview) {
    return (
      <div className={CARD}>
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">소재 교체 확인</p>
        {preview.candidate.headline && (
          <p className="text-sm text-[#191F28] dark:text-[#F2F4F6]">
            새 소재 <b>{preview.candidate.headline}</b>
          </p>
        )}
        <p className="mt-2 text-xs font-semibold text-[#8B95A1]">
          바뀌는 광고 {preview.affected_ads.length}개
        </p>
        <ul className="mt-1 space-y-1">
          {preview.affected_ads.map((a) => (
            <li key={a.ad_id} className="flex items-center gap-2">
              {a.thumbnail_url || a.image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={a.thumbnail_url || a.image_url || ''}
                  alt={a.ad_name}
                  className="h-8 w-8 shrink-0 rounded object-cover"
                />
              ) : (
                <span className="h-8 w-8 shrink-0 rounded bg-[#F2F4F6] dark:bg-[#2D3748]" />
              )}
              <span className="truncate text-xs text-[#4E5968] dark:text-[#9CA3AF]">
                {a.ad_name}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-[#8B95A1]">도착 URL {linkUrl}</p>
        <div className="mt-2 flex gap-2">
          <button
            onClick={approveAndReplace}
            disabled={busy}
            className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40"
          >
            {busy ? '교체 중…' : '승인하고 교체'}
          </button>
          <button
            onClick={() => {
              setProposal(null);
              setPreview(null);
            }}
            disabled={busy}
            className="px-4 py-2 border border-[#E5E8EB] dark:border-[#2D3748] text-sm rounded-lg disabled:opacity-40"
          >
            취소
          </button>
        </div>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </div>
    );
  }

  // 캠페인/후보 선택 화면(기본).
  return (
    <div className={CARD}>
      <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-2">소재 교체</p>

      {warning && (
        <p className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-900/20 dark:text-amber-300">
          {warning}
        </p>
      )}

      <label className="mb-2 block">
        <span className="text-xs text-[#8B95A1]">대상 캠페인</span>
        <select
          value={resolvedId}
          onChange={(e) => setResolvedId(e.target.value)}
          className="mt-1 w-full rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm"
        >
          <option value="">선택하세요</option>
          {picker.map((c) => (
            <option key={c.campaign_id} value={c.campaign_id}>
              {c.name} ({c.state})
            </option>
          ))}
        </select>
      </label>

      <label className="mb-2 block">
        <span className="text-xs text-[#8B95A1]">광고 시안 세트</span>
        <select
          value={genId}
          onChange={(e) => onSelectGen(e.target.value)}
          disabled={!resolvedId}
          className="mt-1 w-full rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm disabled:opacity-40"
        >
          <option value="">선택하세요</option>
          {gens.map((g) => (
            <option key={g.id} value={g.id}>
              {g.id.slice(0, 8)} ·{' '}
              {g.created_at ? new Date(g.created_at).toLocaleDateString('ko-KR') : g.status}
            </option>
          ))}
        </select>
        {gens.length === 0 && (
          <span className="mt-1 block text-xs text-[#8B95A1]">완료된 광고 시안이 없어요.</span>
        )}
      </label>

      <label className="mb-2 block">
        <span className="text-xs text-[#8B95A1]">도착 URL(랜딩)</span>
        <input
          type="url"
          value={linkUrl}
          onChange={(e) => setLinkUrl(e.target.value)}
          className="mt-1 w-full rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] bg-transparent px-3 py-2 text-sm"
        />
      </label>

      {candidates.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-1.5">
          {[...candidates]
            .sort((a, b) => (a.rank ?? a.idx + 1) - (b.rank ?? b.idx + 1))
            .map((c) => {
              const src = candImg(c);
              return (
                <div
                  key={c.candidate_id}
                  className="shrink-0 w-40 rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] overflow-hidden"
                >
                  {src ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={src} alt={`후보 ${c.idx + 1}`} className="w-40 h-40 object-cover" />
                  ) : (
                    <div className="w-40 h-40 flex items-center justify-center bg-[#F2F4F6] dark:bg-[#161B27] text-xs text-[#B0B8C1]">
                      이미지 없음
                    </div>
                  )}
                  <div className="p-2 space-y-1">
                    <p className="text-[10px] font-semibold text-[#8B95A1]">후보 {c.idx + 1}</p>
                    {c.copy?.headline && (
                      <p className="text-xs font-semibold text-[#191F28] dark:text-[#F2F4F6] leading-snug line-clamp-2">
                        {c.copy.headline}
                      </p>
                    )}
                    <button
                      onClick={() => onPickCandidate(c.candidate_id)}
                      disabled={busy || !resolvedId}
                      className="mt-1 w-full py-1.5 rounded-md border border-[#3182F6]/30 text-[#3182F6] text-[11px] font-semibold hover:bg-[#EBF3FF] dark:hover:bg-[#1E3A5F] disabled:opacity-40"
                    >
                      🔄 이 시안으로 교체
                    </button>
                  </div>
                </div>
              );
            })}
        </div>
      )}
      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 2: 타입체크**

Run: `cd frontend && pnpm exec tsc --noEmit`
Expected: 에러 없음 (`Proposal`·`ActionResult`는 `@/components/manage/types`, `CampaignSummary`는 `@/components/manage/campaigns/types`에 존재 — 예산 카드가 동일 import 사용 중)

- [ ] **Step 3: 커밋**

```bash
git add frontend/src/components/chat/ChatReplaceCreativeCard.tsx
git commit -m "add: ChatReplaceCreativeCard — 후보 선택·프리뷰·승인·집행 챗 카드"
```

---

## Task 6: 프론트 — ChatConversation dispatch 연결

**Files:**
- Modify: `frontend/src/components/chat/ChatConversation.tsx`

- [ ] **Step 1: import 추가** (`ChatConversation.tsx` 상단, `ChatCreateCampaignCard` import(line 36) 근처)

```tsx
import ChatReplaceCreativeCard from './ChatReplaceCreativeCard';
```

- [ ] **Step 2: dispatch 블록 추가** (`campaign_action` 위젯 블록(line 1906~1921) **바로 아래**에 추가)

campaign_id는 빈 값일 수 있다(카드가 picker로 해석) → `data?.campaign_id` 존재 조건을 걸지 않고
위젯 타입만으로 렌더한다.

```tsx
                    {msg.meta?.widget?.type === 'replace_creative' && (
                      <ChatReplaceCreativeCard
                        campaignId={msg.meta.widget.data?.campaign_id ?? ''}
                        campaignName={msg.meta.widget.data?.campaign_name}
                      />
                    )}
```

- [ ] **Step 3: 위젯 data 타입 확장** (`ChatConversation.tsx`, widget data 타입 정의부 line 215~216 — `prefill`/`action` 곁에)

```tsx
    campaign_id?: string; // replace_creative 위젯 — 소재 교체 대상 캠페인(빈 값이면 카드가 picker)
    campaign_name?: string; // replace_creative 위젯 — 캠페인명(이름→id 해석용)
```

- [ ] **Step 4: 타입체크·빌드**

Run: `cd frontend && pnpm exec tsc --noEmit && pnpm build`
Expected: 성공(에러·타입 오류 없음)

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/chat/ChatConversation.tsx
git commit -m "add: 챗 replace_creative 위젯 dispatch — ChatReplaceCreativeCard 렌더 연결"
```

---

## Task 7: 엔드투엔드 검증 (Claude Preview, mock)

**Files:** 없음 (검증 전용)

- [ ] **Step 1: dev 서버 기동 + 챗 흐름 관찰**

`preview_start`로 프론트 dev 서버를 띄우고, 챗에서 아래를 실제로 구동해 관찰한다(mock 모드라 끝까지 돈다).
1. 채팅에 "○○ 캠페인 소재 바꿔줘"(이름만) 입력 → `replace_creative` 카드가 뜨고, **대상 캠페인이 이름으로 자동 해석**되는지(못 찾으면 캠페인 드롭다운으로 선택 가능한지).
2. 광고 시안 세트 드롭다운 선택 → 후보 카드가 뜨는지. 도착 URL 입력이 보이는지.
3. "🔄 이 시안으로 교체" 클릭 → 프리뷰에 **새 소재 + 바뀌는 광고들의 이름·썸네일**이 뜨는지.
4. "승인하고 교체" 클릭 → "✓ 소재를 교체했어요"(또는 pending이면 "검토 대기 중") + 승인 ID가 뜨는지.

스크린샷·콘솔/네트워크 로그를 증거로 공유한다.

- [ ] **Step 2: 성공 기준 확인**

mock 모드 한 세션에서 "캠페인 이름으로 지정 → 캠페인 해석 → 후보 고름 → 영향 광고(이름·썸네일) 프리뷰 → 승인하고 교체 → 성공/검토대기 결과"가 끊김 없이 완주하면 완료.
