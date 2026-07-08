// 실 캠페인 차트 — 일자별 지출 vs 일예산(기준선) (Recharts · lifetime)
'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DayPoint } from './types';

const won = (v: number) => `₩${v.toLocaleString()}`;

export default function DeliveryChart({
  series,
  dailyBudget,
}: {
  series: DayPoint[];
  dailyBudget: number;
}) {
  const maxSpend = series.reduce((a, s) => Math.max(a, s.spend_krw), 0);
  const maxY = Math.max(dailyBudget, maxSpend) * 1.15 || 1;

  return (
    <ResponsiveContainer width="100%" height={190}>
      <BarChart data={series} margin={{ top: 16, right: 16, left: 4, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke="#E5E8EB" strokeDasharray="3 3" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 10, fill: '#8B95A1' }}
          interval="preserveStartEnd"
          tickLine={false}
          axisLine={{ stroke: '#E5E8EB' }}
        />
        <YAxis
          domain={[0, maxY]}
          width={46}
          tick={{ fontSize: 10, fill: '#8B95A1' }}
          tickFormatter={(v) => `₩${Math.round(v / 1000)}k`}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          formatter={(value) => won(Number(value))}
          labelStyle={{ color: '#191F28' }}
          contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E5E8EB' }}
        />
        {/* 일예산 미상(0, 예: 보관 캠페인은 광고세트 예산 조회 불가)이면 '일예산 ₩0' 오해 방지를 위해 기준선 숨김 — KPI 카드의 '—'와 표기 통일 */}
        {dailyBudget > 0 && (
          <ReferenceLine
            y={dailyBudget}
            stroke="#8B95A1"
            strokeDasharray="4 3"
            label={{
              value: `일예산 ${won(dailyBudget)}`,
              position: 'insideTopRight',
              fontSize: 10,
              fill: '#8B95A1',
            }}
          />
        )}
        <Bar dataKey="spend_krw" name="지출" fill="#2563EB" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
