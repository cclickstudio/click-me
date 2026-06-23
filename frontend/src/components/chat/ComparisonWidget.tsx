'use client';

// 시뮬레이션 비교 위젯 — 선택한 2개의 결과 KPI를 나란히 비교(T14)
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Picked = { id: string; title: string };
type Summary = Record<string, unknown>;

const pct = (n: unknown) => (typeof n === 'number' ? `${(n * 100).toFixed(0)}%` : '—');
const sc = (n: unknown) => (typeof n === 'number' ? `${n.toFixed(2)}/5` : '—');

export default function ComparisonWidget({ items }: { items: Picked[] }) {
  const [data, setData] = useState<(Summary | null)[] | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const results = await Promise.all(
        items.map(async (it) => {
          try {
            return (await api.chat.resultSummary('sim', it.id)) as Summary;
          } catch {
            return null;
          }
        }),
      );
      if (alive) setData(results);
    })();
    return () => {
      alive = false;
    };
  }, [items]);

  const rows = [
    { label: '클릭 의향률', fmt: pct, key: 'click_intent_rate' },
    { label: '구매의도', fmt: sc, key: 'purchase_intent' },
    { label: '신뢰도', fmt: sc, key: 'trust_avg' },
    { label: '거부율', fmt: pct, key: 'rejection_rate' },
  ];

  return (
    <div className="mt-1 w-full rounded-xl border border-[#E5E8EB] dark:border-[#2D3748] bg-white dark:bg-[#1C2333] p-3 overflow-x-auto">
      {!data ? (
        <p className="text-xs text-[#B0B8C1] py-1">결과를 불러오는 중…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[#8B95A1] text-xs">
              <th className="text-left py-1.5 pr-2">지표</th>
              {items.map((it) => (
                <th key={it.id} className="text-right py-1.5 px-2 text-[#191F28] dark:text-[#F2F4F6] truncate max-w-[120px]">
                  {it.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-[#4E5968] dark:text-[#9CA3AF]">
            {rows.map((row) => (
              <tr key={row.key} className="border-t border-[#F2F4F6] dark:border-[#252D3D]">
                <td className="py-1.5 pr-2">{row.label}</td>
                {data.map((d, i) => (
                  <td key={i} className="text-right py-1.5 px-2 tabular-nums">
                    {d ? row.fmt(d[row.key]) : '실패'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
