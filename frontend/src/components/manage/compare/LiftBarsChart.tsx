// 성과 비교 — 오가닉 vs 광고 도달·노출 그룹 막대 (Recharts)
'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { BoardRow } from './types';

const fmt = (v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${v}`);

export default function LiftBarsChart({ row }: { row: BoardRow }) {
  const { organic, paid } = row.lift;
  const data = [
    { metric: '도달', 오가닉: organic.reach, 광고: paid.reach },
    { metric: '노출', 오가닉: organic.impressions, 광고: paid.impressions },
  ];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }} barGap={4}>
        <CartesianGrid vertical={false} stroke="#E5E8EB" strokeDasharray="3 3" />
        <XAxis
          dataKey="metric"
          tick={{ fontSize: 11, fill: '#8B95A1' }}
          tickLine={false}
          axisLine={{ stroke: '#E5E8EB' }}
        />
        <YAxis
          tickFormatter={fmt}
          width={40}
          tick={{ fontSize: 10, fill: '#8B95A1' }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(v) => Number(v).toLocaleString()}
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E5E8EB' }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="오가닉" fill="#38BDF8" radius={[4, 4, 0, 0]} />
        <Bar dataKey="광고" fill="#6366F1" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
