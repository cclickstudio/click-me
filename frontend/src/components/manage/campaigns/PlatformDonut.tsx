// 플랫폼별 노출 구성비 — 도넛(Recharts) + 범례
'use client';

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { PlatformMetrics } from './types';

const COLORS: Record<string, string> = {
  instagram: '#E1306C',
  facebook: '#1877F2',
  audience_network: '#8B95A1',
  messenger: '#00B2FF',
};
const LABELS: Record<string, string> = {
  facebook: 'Facebook',
  instagram: 'Instagram',
  audience_network: 'Audience Network',
  messenger: 'Messenger',
};
const color = (p: string) => COLORS[p] ?? '#8B95A1';

export default function PlatformDonut({ rows }: { rows: PlatformMetrics[] }) {
  const total = rows.reduce((a, r) => a + r.impressions, 0) || 1;
  return (
    <div className="flex h-full w-full flex-col items-center gap-4">
      <div className="min-h-[9rem] w-full flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={rows}
              dataKey="impressions"
              nameKey="platform"
              innerRadius="52%"
              outerRadius="78%"
              paddingAngle={2}
              stroke="none"
            >
              {rows.map((r) => (
                <Cell key={r.platform} fill={color(r.platform)} />
              ))}
            </Pie>
            <Tooltip
              formatter={(v, n) => [`노출 ${Number(v).toLocaleString()}`, LABELS[String(n)] ?? String(n)]}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E5E8EB' }}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="w-full shrink-0 space-y-1.5">
        {rows.map((r) => (
          <div key={r.platform} className="flex items-center justify-between gap-3 text-[11px]">
            <span className="flex items-center gap-1.5 font-medium text-[#191F28] dark:text-[#F2F4F6]">
              <span className="h-2 w-2 rounded-full" style={{ background: color(r.platform) }} />
              {LABELS[r.platform] ?? r.platform}
              <span className="text-[#8B95A1]">{Math.round((r.impressions / total) * 100)}%</span>
            </span>
            <span className="tabular-nums text-[#8B95A1]">
              노출 {r.impressions.toLocaleString()} · 클릭 {r.clicks.toLocaleString()} · 지출 ₩
              {r.spend_krw.toLocaleString()}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
