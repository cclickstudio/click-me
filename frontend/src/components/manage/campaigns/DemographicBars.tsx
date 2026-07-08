// 연령×성별 분포 — 그룹 세로 막대(연령 x축, 남/여 2색, 노출 비중 %)
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
import type { DemographicMetrics } from './types';

const MALE = '#2563EB';
const FEMALE = '#F2649B';
// Meta 연령 버킷 정렬 순서(어린 → 많은 나이). 미등록 라벨은 뒤로.
const AGE_ORDER = ['13-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65+'];
const rank = (age: string) => {
  const i = AGE_ORDER.indexOf(age);
  return i === -1 ? AGE_ORDER.length : i;
};

export default function DemographicBars({ rows }: { rows: DemographicMetrics[] }) {
  // 연령별 남/여 노출 집계 (unknown 성별은 분포 왜곡 방지로 제외)
  const byAge = new Map<string, { male: number; female: number }>();
  let total = 0;
  for (const r of rows) {
    const e = byAge.get(r.age) ?? { male: 0, female: 0 };
    if (r.gender === 'male') e.male += r.impressions;
    else if (r.gender === 'female') e.female += r.impressions;
    byAge.set(r.age, e);
    total += r.impressions;
  }
  const pct = (v: number) => (total ? Math.round((v / total) * 1000) / 10 : 0);
  const data = [...byAge.keys()]
    .sort((a, b) => rank(a) - rank(b))
    .map((age) => {
      const e = byAge.get(age)!;
      return { age, 남성: pct(e.male), 여성: pct(e.female), maleImp: e.male, femaleImp: e.female };
    });

  return (
    <div className="h-full min-h-[16rem] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 8, right: 8, left: -8, bottom: 0 }}
          barGap={2}
          barCategoryGap="24%"
        >
          <CartesianGrid vertical={false} stroke="#EEF1F4" />
          <XAxis
            dataKey="age"
            tick={{ fontSize: 11, fill: '#8B95A1' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#8B95A1' }}
            axisLine={false}
            tickLine={false}
            unit="%"
            width={38}
          />
          <Tooltip
            cursor={{ fill: 'rgba(0,0,0,0.04)' }}
            contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E5E8EB' }}
            formatter={(value, name, item) => {
              const imp = name === '남성' ? item?.payload?.maleImp : item?.payload?.femaleImp;
              return [`${value}% · 노출 ${Number(imp ?? 0).toLocaleString()}`, name];
            }}
          />
          <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
          <Bar dataKey="남성" fill={MALE} radius={[3, 3, 0, 0]} />
          <Bar dataKey="여성" fill={FEMALE} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
