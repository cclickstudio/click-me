// 실 캠페인 전달 차트 — 누적 지출 vs 일예산(기준선) + 게재 중단 마커 (Recharts)
'use client';

import {
  Area,
  ComposedChart,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { HourPoint } from './types';

const won = (v: number) => `₩${v.toLocaleString()}`;

export default function DeliveryChart({
  series,
  dailyBudget,
  blockReason,
}: {
  series: HourPoint[];
  dailyBudget: number;
  blockReason?: string | null;
}) {
  let cum = 0;
  const data = series.map((p) => {
    cum += p.spend_krw;
    return {
      label: `${String(p.hour).padStart(2, '0')}시`,
      cum,
      spend: p.spend_krw,
      impressions: p.impressions,
    };
  });

  // 게재 차단(잔액 부족 등)이면 현재(마지막) 누적 지점에 중단 마커 — "지금 여기서 멈춤"
  const stopped = Boolean(blockReason) && data.length > 0;
  const stopIdx = data.length - 1;
  const maxY = Math.max(dailyBudget, cum) * 1.15 || 1;

  return (
    <ResponsiveContainer width="100%" height={190}>
      <ComposedChart data={data} margin={{ top: 16, right: 16, left: 4, bottom: 0 }}>
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
        <Area
          type="monotone"
          dataKey="cum"
          name="누적 지출"
          stroke="#3182F6"
          strokeWidth={2}
          fill="#3182F6"
          fillOpacity={0.1}
        />
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
        {stopped && (
          <ReferenceDot
            x={data[stopIdx].label}
            y={data[stopIdx].cum}
            r={5}
            fill="#E5484D"
            stroke="#fff"
            strokeWidth={2}
            label={{
              value: `게재 중단${blockReason ? ` · ${blockReason}` : ''}`,
              position: 'top',
              fontSize: 10,
              fill: '#E5484D',
            }}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
