'use client';

// 시뮬레이션 비교 위젯 — 선택한 2개의 결과 KPI를 나란히 비교(T14)
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';

type Picked = { id: string; title: string };
type Summary = Record<string, unknown>;

const pct = (n: unknown) =>
  typeof n === 'number' ? `${(n * 100).toFixed(0)}%` : '—';
const sc = (n: unknown) => (typeof n === 'number' ? `${n.toFixed(2)}/5` : '—');

export default function ComparisonWidget({ items }: { items: Picked[] }) {
  const [data, setData] = useState<(Summary | null)[] | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const results = await Promise.all(
        items.map(async it => {
          try {
            return (await api.chat.resultSummary('sim', it.id)) as Summary;
          } catch {
            return null;
          }
        })
      );
      if (alive) setData(results);
    })();
    return () => {
      alive = false;
    };
  }, [items]);

  // higherBetter: 값이 클수록 좋은 지표(거부율만 반대). isPct: 0~1 비율 표기.
  const rows = [
    {
      label: '클릭 의향률',
      fmt: pct,
      key: 'click_intent_rate',
      higherBetter: true,
      isPct: true,
    },
    {
      label: '구매의도',
      fmt: sc,
      key: 'purchase_intent',
      higherBetter: true,
      isPct: false,
    },
    {
      label: '신뢰도',
      fmt: sc,
      key: 'trust_avg',
      higherBetter: true,
      isPct: false,
    },
    {
      label: '거부율',
      fmt: pct,
      key: 'rejection_rate',
      higherBetter: false,
      isPct: true,
    },
  ];

  // 두 런(2번째 − 1번째) 차이 — 부호·개선 여부 색으로(거부율은 감소가 개선).
  const showDelta = items.length === 2;
  function delta(key: string, isPct: boolean, higherBetter: boolean) {
    const a = data?.[0]?.[key];
    const b = data?.[1]?.[key];
    if (typeof a !== 'number' || typeof b !== 'number') return null;
    const diff = b - a;
    const sign = diff > 0 ? '+' : '';
    const txt = isPct
      ? `${sign}${(diff * 100).toFixed(0)}%p`
      : `${sign}${diff.toFixed(2)}`;
    const improved = diff === 0 ? 0 : diff > 0 === higherBetter ? 1 : -1;
    return { txt, improved };
  }

  return (
    <div className='mt-1 w-full rounded-xl border border-line bg-card p-3 overflow-x-auto'>
      {!data ? (
        <p className='text-xs text-ink-muted py-1'>결과를 불러오는 중…</p>
      ) : (
        <table className='w-full text-sm'>
          <thead>
            <tr className='text-ink-tertiary text-xs'>
              <th className='text-left py-1.5 pr-2'>지표</th>
              {items.map(it => (
                <th
                  key={it.id}
                  className='text-right py-1.5 px-2 text-ink truncate max-w-[120px]'>
                  {it.title}
                </th>
              ))}
              {showDelta && <th className='text-right py-1.5 pl-2'>차이</th>}
            </tr>
          </thead>
          <tbody className='text-ink-secondary'>
            {rows.map(row => {
              const d = showDelta
                ? delta(row.key, row.isPct, row.higherBetter)
                : null;
              return (
                <tr
                  key={row.key}
                  className='border-t border-line'>
                  <td className='py-1.5 pr-2'>{row.label}</td>
                  {data.map((dd, i) => (
                    <td key={i} className='text-right py-1.5 px-2 tabular-nums'>
                      {dd ? row.fmt(dd[row.key]) : '실패'}
                    </td>
                  ))}
                  {showDelta && (
                    <td
                      className={`text-right py-1.5 pl-2 tabular-nums font-semibold ${
                        !d || d.improved === 0
                          ? 'text-ink-tertiary'
                          : d.improved === 1
                            ? 'text-[#00C471]'
                            : 'text-[#F04452]'
                      }`}>
                      {d ? d.txt : '—'}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
