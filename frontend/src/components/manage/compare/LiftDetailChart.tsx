// B 뷰 — 선택 게시물의 오가닉 vs 광고 막대 비교 (도달·노출)
import type { BoardRow } from './types';

function Bars({ label, organic, paid, max }: { label: string; organic: number; paid: number; max: number }) {
  const pct = (v: number) => `${Math.max(2, (v / max) * 100)}%`;
  return (
    <div className="mb-3">
      <p className="text-xs text-[#8B95A1] mb-1">{label}</p>
      <div className="flex items-center gap-2 mb-1">
        <div className="h-3.5 rounded bg-sky-400" style={{ width: pct(organic) }} />
        <span className="text-[11px] text-[#8B95A1] tabular-nums">{organic.toLocaleString()}</span>
      </div>
      <div className="flex items-center gap-2">
        <div className="h-3.5 rounded bg-[#6366F1]" style={{ width: pct(paid) }} />
        <span className="text-[11px] text-[#8B95A1] tabular-nums">{paid.toLocaleString()}</span>
      </div>
    </div>
  );
}

export function LiftDetailChart({ row }: { row: BoardRow }) {
  const { organic, paid } = row.lift;
  const reachMax = Math.max(organic.reach, paid.reach, 1);
  const imprMax = Math.max(organic.impressions, paid.impressions, 1);
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-5 py-4">
      <p className="font-bold text-[#191F28] dark:text-[#F2F4F6] mb-3">
        선택: {row.title} — 지표 비교
      </p>
      <Bars label="도달" organic={organic.reach} paid={paid.reach} max={reachMax} />
      <Bars label="노출" organic={organic.impressions} paid={paid.impressions} max={imprMax} />
      <div className="flex items-center gap-4 mt-3 text-[11px] text-[#8B95A1]">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-sky-400" /> 오가닉
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm bg-[#6366F1]" /> 광고
        </span>
      </div>
    </div>
  );
}
