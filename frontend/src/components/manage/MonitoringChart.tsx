// 모니터링 시연 차트 — 기대모델 vs 실측 노출 + 이상구간 (Recharts)
'use client';

import { memo, useMemo } from 'react';
import {
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { RunResult } from './types';

// memo — run이 그대로면(mode·busy 토글 등) Recharts 재조정을 건너뛴다.
function MonitoringChart({ run }: { run: RunResult }) {
  const data = useMemo(
    () =>
      run.expected.map((e, i) => ({
        hour: `${String(i).padStart(2, '0')}시`,
        기대: Math.round(e),
        실측: run.snapshots[i]?.impressions ?? null,
      })),
    [run],
  );
  return (
    <ResponsiveContainer width="100%" height={150}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
        <XAxis
          dataKey="hour"
          tick={{ fontSize: 9, fill: '#8B95A1' }}
          interval="preserveStartEnd"
          tickLine={false}
          axisLine={{ stroke: '#E5E8EB' }}
        />
        <YAxis
          width={40}
          tick={{ fontSize: 9, fill: '#8B95A1' }}
          tickFormatter={(v) => (v >= 1000 ? `${Math.round(v / 1000)}k` : `${v}`)}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #E5E8EB' }} />
        {run.anomaly_hours.map((hr) => (
          <ReferenceLine key={hr} x={data[hr]?.hour} stroke="#E5484D" strokeOpacity={0.35} strokeWidth={6} />
        ))}
        <Line
          type="monotone"
          dataKey="기대"
          stroke="#8B95A1"
          strokeWidth={1.5}
          strokeDasharray="4 3"
          dot={false}
        />
        <Line type="monotone" dataKey="실측" stroke="#3182F6" strokeWidth={2} dot={false} connectNulls />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default memo(MonitoringChart);
