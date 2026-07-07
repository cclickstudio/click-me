// 캠페인별 지출 비중 도넛 — 실측 지출의 구성비(Recharts). PlatformDonut 패턴 재사용.
'use client';

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';

const PALETTE = ['#3182F6', '#F04452', '#F59E0B', '#22C55E', '#8B5CF6', '#8B95A1'];

export function SpendDonut({ rows }: { rows: { name: string; spend_krw: number }[] }) {
  const data = rows.filter((r) => r.spend_krw > 0);
  const total = data.reduce((a, r) => a + r.spend_krw, 0);
  if (total <= 0 || data.length === 0) return null;
  return (
    <div className="flex h-full w-full flex-col items-center gap-3">
      <div className="min-h-[8rem] w-full flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="spend_krw"
              nameKey="name"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={2}
              stroke="none"
            >
              {data.map((r, i) => (
                <Cell key={r.name} fill={PALETTE[i % PALETTE.length]} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v, n) => [`₩${Number(v).toLocaleString()}`, String(n)]}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E5E8EB' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="w-full shrink-0 space-y-1">
        {data.map((r, i) => (
          <div key={r.name} className="flex items-center justify-between gap-2 text-[11px]">
            <span className="flex min-w-0 items-center gap-1.5 font-medium text-ink">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ background: PALETTE[i % PALETTE.length] }}
              />
              <span className="truncate">{r.name}</span>
            </span>
            <span className="shrink-0 tabular-nums text-ink-tertiary">
              {Math.round((r.spend_krw / total) * 100)}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
