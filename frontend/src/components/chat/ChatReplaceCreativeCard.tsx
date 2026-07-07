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
