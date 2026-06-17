// 캠페인 상세 — 시간별 노출(기대 vs 실측, 이상구간 음영) + 요약 KPI 타일
import type { CampaignDetail as Detail } from './types';
import { StateBadge } from './StateBadge';

function MetricChart({ expected, actual, anomalyHours }: { expected: number[]; actual: number[]; anomalyHours: number[] }) {
  const w = 640;
  const h = 140;
  const n = expected.length || 1;
  const max = Math.max(1, ...expected, ...actual);
  const x = (i: number) => (i / (n - 1)) * w;
  const y = (v: number) => h - (v / max) * h;
  const line = (vals: number[]) => vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ');
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-36">
      {anomalyHours.map((hr) => (
        <rect key={hr} x={x(hr) - 4} y={0} width={8} height={h} fill="#E5484D" opacity={0.12} />
      ))}
      <path d={line(expected)} fill="none" stroke="#8B95A1" strokeWidth={1.5} strokeDasharray="4 3" />
      <path d={line(actual)} fill="none" stroke="#3182F6" strokeWidth={2} />
    </svg>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] px-3 py-2.5">
      <p className="text-[11px] text-[#8B95A1]">{label}</p>
      <p className="text-base font-bold text-[#191F28] dark:text-[#F2F4F6] tabular-nums mt-0.5">{value}</p>
    </div>
  );
}

export function CampaignDetail({ detail }: { detail: Detail }) {
  const s = detail.summary;
  return (
    <div className="rounded-2xl border border-[#E5E8EB] dark:border-[#2D3748] px-5 py-4">
      <div className="flex items-center justify-between mb-1">
        <p className="font-bold text-[#191F28] dark:text-[#F2F4F6]">{detail.name} — 시간별 노출</p>
        <StateBadge state={detail.state} />
      </div>
      <div className="flex items-center gap-4 text-[11px] text-[#8B95A1] mb-2">
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 border-t-2 border-dashed border-[#8B95A1]" /> 기대모델
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block w-4 border-t-2 border-[#3182F6]" /> 실측
        </span>
        {detail.anomaly_hours.length > 0 && <span className="text-[#E5484D]">■ 이상구간</span>}
      </div>
      <MetricChart expected={detail.expected} actual={detail.actual} anomalyHours={detail.anomaly_hours} />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 mt-4">
        <Tile label="노출" value={s.impressions.toLocaleString()} />
        <Tile label="도달" value={s.reach.toLocaleString()} />
        <Tile label="지출" value={`₩${s.spend_krw.toLocaleString()}`} />
        <Tile label="소진율" value={`${s.pacing_pct.toFixed(0)}%`} />
        <Tile label="CTR" value={`${(s.ctr * 100).toFixed(1)}%`} />
        <Tile label="CVR" value={`${(s.cvr * 100).toFixed(1)}%`} />
        <Tile label="CPC" value={`₩${s.cpc_krw.toLocaleString()}`} />
        <Tile label="CPM" value={`₩${s.cpm_krw.toLocaleString()}`} />
        <Tile label="전환" value={s.conversions.toLocaleString()} />
        <Tile label="빈도" value={s.frequency.toFixed(2)} />
        <Tile label="일예산" value={`₩${detail.daily_budget_krw.toLocaleString()}`} />
      </div>
    </div>
  );
}
