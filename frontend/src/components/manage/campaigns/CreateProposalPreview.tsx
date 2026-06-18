// 신규 캠페인 생성 제안 미리보기 — Tier 3(사람 승인) + 설정 요약 + 승인/취소
import type { Proposal } from '@/components/manage/types';

type ConfigView = {
  daily_budget_krw: number;
  start_at: string;
  end_at: string;
  objective: string;
  creative_ad_id: string | null;
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-[#F2F4F6] dark:border-[#2D3748] last:border-0">
      <span className="text-sm text-[#8B95A1]">{label}</span>
      <span className="text-sm font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums">{value}</span>
    </div>
  );
}

export function CreateProposalPreview({
  proposal,
  onApprove,
  onCancel,
  busy,
}: {
  proposal: Proposal;
  onApprove: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const cfg = proposal.evidence_metrics.campaign_config as ConfigView | undefined;
  const name = (proposal.evidence_metrics.name as string | undefined) ?? '신규 캠페인';
  const fmtDate = (s?: string) => (s ? s.slice(0, 10) : '-');

  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] p-5 max-w-xl">
      <div className="flex items-center justify-between mb-1">
        <h2 className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{name}</h2>
        <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-bold bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          Tier 3 · 사람 승인 필요
        </span>
      </div>
      <p className="text-xs text-[#8B95A1] mb-4">
        신규 집행은 항상 건별 사용자 승인 — 승인해야 생성 단계로 넘어갑니다.
      </p>

      <div className="rounded-xl bg-[#F9FAFB] dark:bg-[#1A202C] px-4 py-2">
        <Row label="목표" value="트래픽 (클릭)" />
        <Row label="일 예산" value={`₩${proposal.budget_after_krw.toLocaleString()}`} />
        <Row label="집행 기간" value={`${fmtDate(cfg?.start_at)} ~ ${fmtDate(cfg?.end_at)}`} />
        <Row label="예상 총지출" value={`₩${proposal.max_total_spend_krw.toLocaleString()}`} />
        {cfg?.creative_ad_id && <Row label="소재 ID" value={cfg.creative_ad_id} />}
      </div>

      <div className="flex items-center justify-end gap-2 mt-4">
        <button
          onClick={onCancel}
          disabled={busy}
          className="px-4 py-2 text-sm font-medium rounded-lg border border-[#E5E8EB] dark:border-[#2D3748] text-[#4E5968] dark:text-[#9CA3AF] disabled:opacity-40"
        >
          취소
        </button>
        <button
          onClick={onApprove}
          disabled={busy}
          className="px-4 py-2 bg-[#3182F6] text-white text-sm font-medium rounded-lg hover:bg-[#1B6EEB] disabled:opacity-40"
        >
          {busy ? '생성 중…' : '승인하고 생성'}
        </button>
      </div>
    </div>
  );
}
