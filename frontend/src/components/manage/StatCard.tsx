// KPI 스탯 카드 — 값 + (있으면) 실측 스파크라인·추세 델타. 모니터링·예산 등 manage 공용.
import { OriginTag } from '@/components/manage/ValueOrigin';
import { Sparkline } from '@/components/manage/monitoring/Sparkline';

function DeltaTag({ delta, label }: { delta: number | null; label: string }) {
  if (delta == null) return null;
  const pct = Math.round(delta * 100);
  if (pct === 0) return <span className="text-[10px] text-[#8B95A1]">{label} →0%</span>;
  const up = pct > 0;
  return (
    <span
      className={`text-[10px] font-medium ${
        up ? 'text-green-600 dark:text-green-400' : 'text-red-500 dark:text-red-400'
      }`}
    >
      {label} {up ? '▲' : '▼'}
      {Math.abs(pct)}%
    </span>
  );
}

export function StatCard({
  label,
  value,
  sub,
  origin,
  alert = false,
  delta,
  deltaLabel = '7일',
  series,
}: {
  label: string;
  value: string;
  sub?: string;
  origin?: 'setting' | 'computed';
  alert?: boolean;
  delta?: number | null; // 등락률(비율) — 실측 시계열에서 계산된 값만 전달(합성 금지)
  deltaLabel?: string;
  series?: number[]; // 있으면 우측에 미니 추세선 — 실측 일별 시계열만
}) {
  const hasSpark = series != null && series.filter((v) => Number.isFinite(v)).length >= 2;
  return (
    <div
      className={`bg-white dark:bg-[#1C2333] border rounded-2xl p-5 ${
        alert ? 'border-[#E5484D]' : 'border-[#E5E8EB] dark:border-[#2D3748]'
      }`}
    >
      <p className="text-xs text-[#8B95A1] mb-1">
        {label}
        {origin && <OriginTag origin={origin} />}
      </p>
      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <p
            className={`text-2xl font-bold tabular-nums ${
              alert ? 'text-[#E5484D]' : 'text-[#191F28] dark:text-[#F2F4F6]'
            }`}
          >
            {value}
          </p>
          {(delta !== undefined || sub) && (
            <p className="mt-0.5 flex items-center gap-1.5">
              {delta !== undefined && <DeltaTag delta={delta} label={deltaLabel} />}
              {sub && <span className="text-[11px] text-[#B0B8C1]">{sub}</span>}
            </p>
          )}
        </div>
        {hasSpark && (
          <div className="shrink-0 pb-0.5">
            <Sparkline values={series} width={72} height={26} />
          </div>
        )}
      </div>
    </div>
  );
}
